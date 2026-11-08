import json
from pathlib import Path
from .contracts import require, text, ident, encode, now
from .changes import normalize, capture, baseline_state


def context(store, workspace_root, action, task_id=None, scope=None, idempotency_key=None, description="本次开发", session_id=None):
    require(action in {"start", "resume", "complete"}, "INVALID_ACTION", "Use start, resume or complete")
    root = Path(workspace_root).resolve(strict=True)
    if action == "start":
        text(idempotency_key, "idempotency_key", 200)
        require(scope is None or isinstance(scope, list) and bool(scope), "INVALID_SCOPE", "Scope must be a nonempty path list")
        scopes = sorted(set(normalize(p, allow_root=True) for p in (scope if scope is not None else ["."])))
        require(not any(any(c in p for c in "*?[]") for p in scopes), "UNSUPPORTED_SCOPE_PATTERN",
                "Scope accepts literal files/directories only; replace ui/** with ui and test_*.py with tests or explicit filenames")
        require(len(scopes) <= 50, "INVALID_SCOPE", "At most 50 bounded scope entries")
        text(description, "description", 500)
        with store.transaction() as db:
            wid, root = store.workspace(db, root)
            existing = db.execute("SELECT * FROM tasks WHERE workspace_id=? AND start_key=?", (wid, idempotency_key)).fetchone()
            if existing:
                require(existing["scope"] == encode(scopes) and existing["description"] == description,
                        "IDEMPOTENCY_CONFLICT", "Task start key changed its scope or description")
                task_id = existing["id"]
            else:
                require(task_id is None, "INVALID_INPUT", "New task ids are allocated by WhoChose")
                baseline = capture(store, root, scopes)
                prior = db.execute("SELECT dirty FROM hook_state WHERE workspace_id=? AND session_id=?", (wid, session_id)).fetchone() if session_id else None
                state = baseline_state(baseline)
                if prior and prior["dirty"]:
                    state = "PARTIAL_BASELINE"
                    baseline["limitation"] = "late_start_after_observed_tool; earlier edits are not recoverable"
                task_id = ident("task")
                db.execute("INSERT INTO tasks(id,workspace_id,start_key,scope,description,task_revision,status,created,completed,baseline,baseline_state) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (task_id, wid, idempotency_key, encode(scopes),
                    description, 1, "OPEN", now(), None, encode(baseline), state))
    with store.transaction() as db:
        task = store.task(db, task_id)
        require(Path(task["workspace_root"]) == root, "WORKSPACE_MISMATCH", "Task belongs to a different workspace")
        if session_id:
            state = db.execute("SELECT * FROM hook_state WHERE workspace_id=? AND session_id=?", (task["workspace_id"], session_id)).fetchone()
            require(state is not None, "SESSION_NOT_OBSERVED", "Bind only a Hook-observed session")
            db.execute("UPDATE hook_state SET task_id=? WHERE workspace_id=? AND session_id=?", (task_id, task["workspace_id"], session_id))
        messages = [dict(r) for r in db.execute("SELECT id message_id,digest message_digest,excerpt,length,captured_at FROM hook_messages WHERE workspace_id=?" +
            (" AND session_id=?" if session_id else " AND 0" ) + " ORDER BY captured_at DESC LIMIT 10",
            (task["workspace_id"], session_id) if session_id else (task["workspace_id"],))]
    if action == "complete":
        from .changes import coverage
        text(idempotency_key, "idempotency_key", 200)
        checked = coverage(store, task_id)
        with store.transaction() as db:
            replay, sha = store.replay(db, task_id, "complete_task", idempotency_key, {"action": "complete"})
            if replay:
                return replay
            status = "COMPLETED" if checked["complete_within_inspected_scope"] else "COMPLETED_WITH_GAPS"
            if task["status"] == "OPEN":
                db.execute("UPDATE tasks SET status=?,completed=?,end_snapshot=? WHERE id=?", (status, now(), encode(checked), task_id))
            result = {"task_id": task_id, "task_revision": task["task_revision"], "status": status,
                      "coverage": checked["counts"], "limitations": checked["uninspected"], "semantic_coverage_verified": False}
            store.remember(db, task_id, "complete_task", idempotency_key, sha, result)
            return result
    return {"task_id": task_id, "task_revision": task["task_revision"], "workspace_root": task["workspace_root"],
            "status": task["status"], "baseline_state": task["baseline_state"], "scope": json.loads(task["scope"]),
            "user_message_refs": messages, "semantic_coverage_verified": False}
