"""Record actual task changes and source declarations; never infer intent by keyword."""
import json
import subprocess
from .contracts import require, entries, text, ident, now, encode, digest
from . import changes


def code_reference(store, root, hunk, supplied=None):
    ref = dict(supplied or {})
    path = ref.get("path", hunk["path"])
    require(path == hunk["path"], "CODE_HUNK_MISMATCH", "Code reference must belong to its linked hunk")
    sha = hunk["after_sha256"] or hunk["before_sha256"]
    if hunk["after_sha256"]:
        raw, content = changes.read_code(root, path)
        require(digest(raw) == sha, "CODE_VERSION_CHANGED", "Code changed after the diff was captured")
    else:
        content = changes.blob_text(store, sha)
    line_count = len(content.splitlines())
    start = ref.get("start_line", max(1, hunk["new_start"] or hunk["old_start"]) if line_count else None)
    end = ref.get("end_line", start)
    if start is not None:
        require(type(start) is int and type(end) is int and 1 <= start <= end <= line_count,
                "CODE_RANGE_INVALID", "Reference lines must exist in the stored version")
    else:
        require(end is None, "CODE_RANGE_INVALID", "A file-level link has no end line")
    require(ref.get("file_sha256", sha) == sha and ref.get("revision", "snapshot:" + sha) == "snapshot:" + sha,
            "CODE_VERSION_CHANGED", "Reference does not match the actual snapshot")
    return {"path": path, "start_line": start, "end_line": end, "file_sha256": sha,
            "revision": "snapshot:" + sha, "deleted": hunk["after_sha256"] is None}


def resolve_source(db, task, entry):
    source = entry.get("source_class", "UNKNOWN")
    require(source in {"USER_SPECIFIED", "AI_SUPPLEMENTED", "UNKNOWN"}, "INVALID_SOURCE", "Use the three source classes")
    refs = []
    if source == "USER_SPECIFIED":
        user_refs = entry.get("user_decision_refs", [])
        require(isinstance(user_refs, list) and 0 < len(user_refs) <= 20, "USER_EVIDENCE_REQUIRED", "Link an observed explicit user decision")
        origins, confirmations = set(), set()
        for reference in user_refs:
            row = db.execute("SELECT * FROM user_decisions WHERE id=? AND revision=? AND workspace_id=?", (reference.get("record_id"), reference.get("revision"), task["workspace_id"])).fetchone()
            require(row is not None, "USER_DECISION_NOT_FOUND", "User decision ref belongs to no known workspace revision")
            latest = db.execute("SELECT max(revision) FROM user_decisions WHERE id=?", (row["id"],)).fetchone()[0]
            require(latest == row["revision"], "USER_DECISION_SUPERSEDED", "A superseded user decision cannot confirm a current choice")
            data = json.loads(row["data"])
            require(data["intent"] != "SCOPE_AUTHORIZATION" and row["behavior_key"] == entry["behavior_key"],
                    "DELEGATION_NOT_CONFIRMATION", "Delegation or a different behavior does not confirm this concrete choice")
            origins.add(data["proposal_origin"])
            confirmations.add(data["user_confirmation"])
            refs.append({"record_id": row["id"], "revision": row["revision"], "title": data["title"],
                         "proposal_origin": data["proposal_origin"], "user_confirmation": data["user_confirmation"], "proposal_summary": data.get("proposal_summary"),
                         "accepted_option": data.get("accepted_option"), "source_evidence_refs": data["source_evidence_refs"]})
        require(len(origins) == 1 and len(confirmations) == 1, "SOURCE_CONFLICT", "Do not merge incompatible source origins")
        origin = origins.pop()
        require(entry.get("proposal_origin", origin) == origin, "SOURCE_CONFLICT", "Retain the original proposer")
        confirmation = confirmations.pop()
        require(entry.get("user_confirmation", confirmation) == confirmation,
                "CONFIRMATION_CONFLICT", "Retain the actual requirement source")
        return source, origin, confirmation, refs
    require(entry.get("user_confirmation", "NONE") != "EXPLICIT", "USER_EVIDENCE_REQUIRED", "Explicit confirmation requires matching user evidence")
    if source == "AI_SUPPLEMENTED":
        notes = entry.get("development_evidence", [])
        require(isinstance(notes, list) and 0 < len(notes) <= 10, "AI_EVIDENCE_REQUIRED", "Do not infer AI origin from missing user messages")
        for note in notes:
            require(isinstance(note, dict) and note.get("kind") == "DEVELOPMENT_NOTE", "INVALID_EVIDENCE", "Supply a development-time declaration")
            text(note.get("text"), "development_evidence.text", 2000)
        require(entry.get("proposal_origin", "AI") == "AI", "SOURCE_CONFLICT", "AI selection requires AI origin")
        return source, "AI", "NONE", [{"kind": "DEVELOPMENT_NOTE", "text": n["text"], "captured_at": now(),
                                      "provenance": "agent_recorded_during_open_task", "semantic_verified": False} for n in notes]
    require(entry.get("proposal_origin", "UNKNOWN") == "UNKNOWN", "SOURCE_CONFLICT", "Do not claim an unsupported proposer")
    return "UNKNOWN", "UNKNOWN", "UNCERTAIN", []


def save(store, task_id, batch, hunk_refs, key):
    entries(batch)
    require(isinstance(hunk_refs, list) and len(hunk_refs) <= 2000, "INVALID_HUNK_REFS", "Supply bounded hunk refs")
    payload = {"entries": batch, "hunk_refs": hunk_refs}
    with store.connect() as db:
        store.task(db, task_id)
        replay, _ = store.replay(db, task_id, "save_implementation_choices", key, payload)
        if replay:
            return replay
    current = changes.refresh(store, task_id)
    available = {h["hunk_id"]: h for h in current["hunks"]}
    linked = set()
    result_records = []
    warnings = []
    with store.transaction() as db:
        task = store.task(db, task_id)
        replay, sha = store.replay(db, task_id, "save_implementation_choices", key, payload)
        if replay:
            return replay
        require(task["status"] == "OPEN", "TASK_CLOSED", "Create a new task before changing completed work")
        for entry in batch:
            kind = entry.get("kind")
            require(kind in {"DECISION", "ORDINARY_CHANGE"}, "INVALID_KIND", "Use DECISION or ORDINARY_CHANGE")
            refs = entry.get("hunk_refs", [])
            require(isinstance(refs, list) and refs and all(r in available and r in hunk_refs for r in refs),
                    "HUNK_NOT_CURRENT", "An implemented record must link current actual task changes")
            linked.update(refs)
            block_key = text(entry.get("functional_block_key"), "functional_block_key", 100)
            block_name = text(entry.get("functional_block_name", block_key), "functional_block_name", 100)
            block = db.execute("SELECT id FROM functional_blocks WHERE task_id=? AND block_key=?", (task_id, block_key)).fetchone()
            block_id = block["id"] if block else ident("block")
            if not block:
                db.execute("INSERT INTO functional_blocks VALUES(?,?,?,?)", (block_id, task_id, block_key, block_name))
            code_refs = entry.get("code_refs", [])
            require(isinstance(code_refs, list) and len(code_refs) <= 100, "INVALID_CODE_REFS", "At most 100 file references")
            codes = []
            if code_refs:
                for ref in code_refs:
                    candidates = [available[r] for r in refs if available[r]["path"] == ref.get("path")]
                    require(candidates, "CODE_HUNK_MISMATCH", "Code path is not part of the linked changes")
                    codes.append(code_reference(store, task["workspace_root"], candidates[0], ref))
            else:
                for ref in refs:
                    code = code_reference(store, task["workspace_root"], available[ref])
                    if code not in codes:
                        codes.append(code)
            if kind == "ORDINARY_CHANGE":
                require(entry.get("impact_level", "NORMAL") != "HIGH", "HIGH_IMPACT_IS_DECISION", "Do not hide high-impact choices as ordinary")
                summary = text(entry.get("summary"), "summary", 1000)
                category = text(entry.get("category", "其他"), "category", 100)
                reason = entry.get("exclusion_reason")
                if reason is not None:
                    text(reason, "exclusion_reason", 500)
                rid, revision = ident("ordinary"), 1
                data = {"kind": kind, "summary": summary, "category": category, "exclusion_reason": reason}
                db.execute("INSERT INTO ordinary_changes VALUES(?,?,?,?,?)", (rid, task_id, block_id, encode(data), now()))
                classification = "EXCLUDED_WITH_REASON" if reason else "ORDINARY_EXPLAINED"
            else:
                behavior = text(entry.get("behavior_key"), "behavior_key", 200)
                title = text(entry.get("title"), "title", 200)
                impact = text(entry.get("user_visible_consequence"), "user_visible_consequence", 2000)
                difference = text(entry.get("meaningful_difference"), "meaningful_difference", 1000)
                level = entry.get("impact_level", "NORMAL")
                require(level in {"NORMAL", "HIGH"}, "INVALID_IMPACT", "Use NORMAL or HIGH")
                require(entry.get("ai_subclass", "UNDETERMINED") in {"CONSTRAINT_DERIVED", "AUTONOMOUS_TRADEOFF", "UNDETERMINED"}, "INVALID_AI_SUBCLASS", "Unsupported AI explanation subtype")
                source, origin, confirmation, sources = resolve_source(db, task, entry)
                rationale_origin = entry.get("rationale_origin", "MISSING")
                require(rationale_origin in {"CONTEMPORANEOUS", "RETROSPECTIVE", "MISSING"}, "INVALID_RATIONALE", "Invalid reason provenance")
                rationale = entry.get("rationale")
                if rationale_origin != "MISSING":
                    text(rationale, "rationale", 2000)
                else:
                    require(not rationale, "RATIONALE_CONFLICT", "Do not attach a reason labeled missing")
                basis = entry.get("consequence_basis", "CODE_INFERRED")
                require(basis in {"RUNTIME_VERIFIED", "CODE_INFERRED", "UNVERIFIED"}, "INVALID_BASIS", "Invalid consequence basis")
                runtime_refs = entry.get("runtime_evidence_refs", [])
                if basis == "RUNTIME_VERIFIED":
                    require(runtime_refs, "RUNTIME_EVIDENCE_REQUIRED", "Code presence is not a successful run")
                    for evidence_id in runtime_refs:
                        evidence = db.execute("SELECT * FROM evidence_refs WHERE id=? AND task_id=? AND kind='RUNTIME'", (evidence_id, task_id)).fetchone()
                        require(evidence is not None, "RUNTIME_EVIDENCE_REQUIRED", "Runtime evidence was not recorded by the verifier")
                        run = json.loads(evidence["data"])
                        require(run["exit_code"] == 0 and all(run["code_hashes"].get(c["path"]) == c["file_sha256"] for c in codes),
                                "RUNTIME_VERSION_MISMATCH", "Successful execution must match these actual code versions")
                old = db.execute("SELECT * FROM decisions WHERE workspace_id=? AND behavior_key=?", (task["workspace_id"], behavior)).fetchone()
                if old:
                    require(entry.get("record_id") == old["id"] and entry.get("expected_revision") == old["revision"],
                            "REVISION_CONFLICT", "Read and explicitly supersede the current implementation choice")
                    rid, revision = old["id"], old["revision"] + 1
                    db.execute("UPDATE decisions SET revision=? WHERE id=?", (revision, rid))
                else:
                    require(not entry.get("record_id") and entry.get("expected_revision", 0) == 0, "REVISION_CONFLICT", "No prior choice exists")
                    rid, revision = ident("decision"), 1
                    db.execute("INSERT INTO decisions VALUES(?,?,?,?)", (rid, task["workspace_id"], behavior, revision))
                data = {"kind": kind, "behavior_key": behavior, "title": title, "user_visible_consequence": impact,
                    "meaningful_difference": difference, "impact_level": level, "source_class": source,
                    "proposal_origin": origin, "user_confirmation": confirmation, "source_evidence_refs": sources,
                    "ai_subclass": entry.get("ai_subclass", "UNDETERMINED") if source == "AI_SUPPLEMENTED" else None,
                    "rationale_origin": rationale_origin, "rationale": rationale,
                    "rationale_captured_at": now() if rationale else None, "consequence_basis": basis,
                    "runtime_evidence_refs": runtime_refs, "semantic_verified": False,
                    "supersedes": {"record_id": rid, "revision": revision - 1} if old else None}
                db.execute("INSERT INTO decision_revisions VALUES(?,?,?,?,?,?)", (rid, revision, task_id, block_id, encode(data), now()))
                if source == "AI_SUPPLEMENTED" and rationale_origin == "MISSING":
                    warnings.append({"code": "AI_RATIONALE_MISSING", "record_id": rid, "revision": revision,
                        "behavior_key": behavior,
                        "message": "选择已保存，但缺少开发时理由。仅补记真实已有的依据；事后解释应标为 RETROSPECTIVE，确实未记录时保留 MISSING。"})
                classification = "DECISION_LINKED"
            for code in codes:
                db.execute("INSERT INTO code_links VALUES(?,?,?,?,?)", (ident("code"), task_id, rid, revision, encode(code)))
            for ref in refs:
                db.execute("INSERT INTO hunk_links VALUES(?,?,?,?,?)", (ref, rid, revision, classification, entry.get("exclusion_reason")))
            result_records.append({"record_id": rid, "revision": revision, "kind": kind, "validation": "references_valid_semantics_agent_interpreted"})
        require(linked == set(hunk_refs), "UNASSIGNED_HUNK_REFS", "Every supplied hunk ref must belong to at least one entry")
        result = {"records": result_records, "replayed": False, "semantic_verified": False, "warnings": warnings}
        store.remember(db, task_id, "save_implementation_choices", key, sha, result)
    checked = changes.coverage(store, task_id)
    with store.transaction() as db:
        db.execute("UPDATE hook_state SET dirty=?,last_recorded_change_id=? WHERE task_id=?",
                   (int(bool(checked["counts"]["UNREVIEWED"])), checked["generation"], task_id))
    return result


def record_run(store, task_id, command, purpose, timeout=30):
    """Explicit CLI-only execution. Never exposed as an additional MCP tool."""
    require(isinstance(command, list) and command and all(isinstance(p, str) for p in command), "INVALID_COMMAND", "Supply a command argument list")
    text(purpose, "purpose", 500)
    with store.connect() as db:
        task = store.task(db, task_id)
    before = changes.capture(store, task["workspace_root"], json.loads(task["scope"]))
    hashes = {p: e["sha256"] for p, e in before["files"].items() if e["status"] == "captured"}
    try:
        run = subprocess.run(command, cwd=task["workspace_root"], capture_output=True, timeout=min(max(timeout, 1), 60), stdin=subprocess.DEVNULL)
        after = changes.capture(store, task["workspace_root"], json.loads(task["scope"]))
        after_hashes = {p: e["sha256"] for p, e in after["files"].items() if e["status"] == "captured"}
        hashes = {p: sha for p, sha in hashes.items() if after_hashes.get(p) == sha}
        data = {"command": command, "purpose": purpose, "exit_code": run.returncode, "code_hashes": hashes,
                "stdout_sha256": digest(run.stdout), "stderr_sha256": digest(run.stderr), "completed_at": now(),
                "semantic_verified": False}
    except subprocess.TimeoutExpired:
        data = {"command": command, "purpose": purpose, "exit_code": None, "code_hashes": {}, "timed_out": True, "completed_at": now()}
    eid = ident("run")
    with store.transaction() as db:
        db.execute("INSERT INTO evidence_refs VALUES(?,?,?,?,?)", (eid, task_id, "RUNTIME", encode(data), now()))
    return {"evidence_id": eid, **data}
