import json
from .contracts import require, text, entries, ident, now, encode
from .provenance import validate_message_refs, validate_project_refs


def save_user(store, task_id, batch, refs, key):
    entries(batch)
    with store.transaction() as db:
        task = store.task(db, task_id)
        payload = {"entries": batch, "user_message_refs": refs}
        replay, sha = store.replay(db, task_id, "save_user_decisions", key, payload)
        if replay:
            return replay
        require(task["status"] == "OPEN", "TASK_CLOSED", "Resume with a new task to revise completed work")
        validated = validate_message_refs(db, task["workspace_id"], refs) if refs else []
        results = []
        for entry in batch:
            behavior = text(entry.get("behavior_key"), "behavior_key", 200)
            title = text(entry.get("title"), "title", 200)
            intent = entry.get("intent")
            require(intent in {"DIRECT_INSTRUCTION", "ACCEPTED_PROPOSAL", "SCOPE_AUTHORIZATION", "PROJECT_REQUIREMENT"},
                    "INTENT_NOT_EXPLICIT", "Ambiguous preferences and forwarded plans are not explicit decisions")
            if intent == "PROJECT_REQUIREMENT":
                require(not entry.get("message_ids") and not refs, "SOURCE_CONFLICT",
                        "Cite project documents separately from current user messages")
                require(entry.get("proposal_origin", "UNKNOWN") == "UNKNOWN"
                        and entry.get("user_confirmation", "PROJECT_DOCUMENT") == "PROJECT_DOCUMENT"
                        and entry.get("source_class", "USER_SPECIFIED") == "USER_SPECIFIED",
                        "CONFIRMATION_CONFLICT", "Project requirements are authoritative, not observed personal confirmation")
                origin, confirmation = "UNKNOWN", "PROJECT_DOCUMENT"
                source_refs = validate_project_refs(task["workspace_root"], entry.get("project_refs"))
            else:
                origin, confirmation = entry.get("proposal_origin"), "EXPLICIT"
                require(entry.get("user_confirmation", "EXPLICIT") == "EXPLICIT" and entry.get("source_class", "USER_SPECIFIED") == "USER_SPECIFIED",
                        "CONFIRMATION_CONFLICT", "Uncertain intent cannot be upgraded by the explicit-decision API")
                require(origin == ("AI" if intent == "ACCEPTED_PROPOSAL" else "USER"), "ORIGIN_CONFLICT", "Retain the actual original proposer")
                if intent == "ACCEPTED_PROPOSAL":
                    text(entry.get("proposal_summary"), "proposal_summary", 1000)
                    text(entry.get("accepted_option"), "accepted_option", 1000)
                require(validated, "MESSAGE_EVIDENCE_REQUIRED", "Supply Hook-observed messages for a chat decision")
                selected_refs = entry.get("message_ids") or [r["message_id"] for r in validated]
                source_refs = [r for r in validated if r["message_id"] in selected_refs]
                require(source_refs and len(source_refs) == len(set(selected_refs)), "INVALID_MESSAGE_REFS", "Entry refers to unavailable original messages")
            old = db.execute("SELECT * FROM user_decisions WHERE workspace_id=? AND behavior_key=? ORDER BY created DESC,revision DESC LIMIT 1", (task["workspace_id"], behavior)).fetchone()
            if old:
                require(entry.get("record_id") == old["id"] and entry.get("expected_revision") == old["revision"],
                        "REVISION_CONFLICT", "Read and explicitly revise the existing decision")
                rid, revision = old["id"], old["revision"] + 1
            else:
                require(not entry.get("record_id") and entry.get("expected_revision", 0) == 0, "REVISION_CONFLICT", "No previous decision exists")
                rid, revision = ident("user"), 1
            data = {"title": title, "behavior_key": behavior, "intent": intent, "proposal_origin": origin,
                    "proposal_summary": entry.get("proposal_summary"), "accepted_option": entry.get("accepted_option"),
                    "source_class": "USER_SPECIFIED", "user_confirmation": confirmation, "source_evidence_refs": source_refs,
                    "scope": entry.get("scope", "task"), "semantic_verified": False,
                    "supersedes": {"record_id": rid, "revision": revision-1} if old else None}
            db.execute("INSERT INTO user_decisions VALUES(?,?,?,?,?,?,?)", (rid, revision, task_id, task["workspace_id"], behavior, encode(data), now()))
            results.append({"record_id": rid, "revision": revision, "validation": "literal_references_valid_semantics_agent_interpreted"})
        result = {"records": results, "replayed": False, "does_not_authorize_host_operations": True}
        store.remember(db, task_id, "save_user_decisions", key, sha, result)
        return result


def get_user(store, task_id, scope=None):
    with store.connect() as db:
        task = store.task(db, task_id)
        rows = db.execute("SELECT u.* FROM user_decisions u WHERE u.workspace_id=? AND u.revision=(SELECT max(v.revision) FROM user_decisions v WHERE v.id=u.id)" +
                          (" AND u.task_id=?" if scope != "relevant_history" else ""),
                          (task["workspace_id"], task_id) if scope != "relevant_history" else (task["workspace_id"],)).fetchall()
        return {"task_id": task_id, "decisions": [{"record_id": r["id"], "revision": r["revision"], "task_id": r["task_id"], **json.loads(r["data"])} for r in rows],
                "semantic_verified": False}
