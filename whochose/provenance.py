"""Host message references prove literal provenance, never natural-language intent."""
import json
from .contracts import require, text, digest, encode, ident, now
from pathlib import Path
from .changes import read_code


def _message_turn_id(turn_id, prompt):
    """Separate a native question reply from its still-running host turn.

    This only identifies a Hook-observed message; it does not validate an
    answer's meaning or establish acceptance of an AI proposal.
    """
    opening = "<send_user_message_question_reply>"
    closing = "</send_user_message_question_reply>"
    envelope = prompt.strip()
    if not (envelope.startswith(opening) and envelope.endswith(closing)):
        return turn_id
    try:
        replies = json.loads(envelope[len(opening):-len(closing)])
        if not isinstance(replies, list) or not replies:
            return turn_id
        question_ids = []
        for reply in replies:
            if (not isinstance(reply, dict)
                    or not all(isinstance(reply.get(key), str)
                               for key in ("questionItemId", "question", "answer"))):
                return turn_id
            item = json.loads(reply["questionItemId"])
            if (not isinstance(item, list) or len(item) != 3
                    or item[0] != "request_user_input_async"
                    or not isinstance(item[1], str) or not item[1].strip()
                    or type(item[2]) is not int or item[2] < 0):
                return turn_id
            question_ids.append(encode(item))
        if len(set(question_ids)) != len(question_ids):
            return turn_id
    except (ValueError, TypeError, RecursionError):
        return turn_id
    # Use question identity, not answer content: a rewritten answer must still
    # conflict rather than silently acquiring a new trusted message reference.
    return "native-reply:" + digest(encode([turn_id, sorted(question_ids)]))


def observe_user_message(store, event):
    require(event.get("hook_event_name") == "UserPromptSubmit" and not event.get("stop_hook_active")
            and not event.get("is_synthetic"), "UNVERIFIED_MESSAGE", "Only actual UserPromptSubmit callbacks can bind messages")
    for key in ("cwd", "session_id", "turn_id", "prompt"):
        text(event.get(key), key, 100000 if key == "prompt" else 2000)
    prompt = event["prompt"].replace("\r\n", "\n").replace("\r", "\n")
    message_turn = _message_turn_id(event["turn_id"], prompt)
    with store.transaction() as db:
        wid, _ = store.workspace(db, event["cwd"])
        old = db.execute("SELECT * FROM hook_messages WHERE workspace_id=? AND session_id=? AND turn_id=?",
                         (wid, event["session_id"], message_turn)).fetchone()
        sha = digest(prompt)
        if old:
            require(old["digest"] == sha, "HOST_TURN_REUSED", "Host turn changed its prompt")
            return {"message_id": old["id"], "message_digest": sha, "excerpt_truncated": old["length"] > 4000}
        mid = ident("message")
        db.execute("INSERT INTO hook_messages VALUES(?,?,?,?,?,?,?,?,?)", (mid, wid, event["session_id"], message_turn,
                   sha, prompt[:4000], len(prompt), now(), "local_host_hook"))
        prior_task = db.execute("SELECT t.status FROM hook_state h JOIN tasks t ON t.id=h.task_id WHERE h.workspace_id=? AND h.session_id=?",
                                (wid, event["session_id"])).fetchone()
        if prior_task and prior_task["status"] != "OPEN":
            # Keep frozen gaps on the old task; a real new prompt begins a new boundary.
            db.execute("UPDATE hook_state SET task_id=NULL,dirty=0,nudge_count=0,last_recorded_change_id=NULL,last_nudge_change_id=NULL WHERE workspace_id=? AND session_id=?",
                       (wid, event["session_id"]))
        db.execute("INSERT INTO hook_state(workspace_id,session_id,turn_id) VALUES(?,?,?) ON CONFLICT(workspace_id,session_id) DO UPDATE SET turn_id=excluded.turn_id,nudge_count=0",
                   (wid, event["session_id"], event["turn_id"]))
        return {"message_id": mid, "message_digest": sha, "excerpt_truncated": len(prompt) > 4000}


def validate_message_refs(db, workspace_id, refs):
    require(isinstance(refs, list) and 0 < len(refs) <= 20, "MESSAGE_EVIDENCE_REQUIRED", "Supply observed message refs and exact quotes")
    result = []
    for ref in refs:
        row = db.execute("SELECT * FROM hook_messages WHERE id=? AND workspace_id=?", (ref.get("message_id"), workspace_id)).fetchone()
        require(row is not None, "MESSAGE_NOT_OBSERVED", "No Hook-observed message exists for this workspace")
        quote = text(ref.get("quote"), "quote", 2000)
        require(ref.get("message_digest") == row["digest"] and quote in row["excerpt"],
                "MESSAGE_QUOTE_MISMATCH", "Digest and quote must match the bounded observed original")
        result.append({"message_id": row["id"], "message_digest": row["digest"], "quote": quote,
                       "captured_at": row["captured_at"], "literal_reference_valid": True, "semantic_verified": False})
    return result


def validate_project_refs(root, refs):
    """Validate document bytes/quotes, without asserting authorship or approval."""
    require(isinstance(refs, list) and 0 < len(refs) <= 20,
            "PROJECT_EVIDENCE_REQUIRED", "Supply project document paths, versions and exact quotes")
    result = []
    for ref in refs:
        require(isinstance(ref, dict), "INVALID_EVIDENCE", "Project ref must be an object")
        path = text(ref.get("path"), "path", 512).replace("\\", "/")
        require(Path(path).suffix.lower() in {".md", ".txt", ".rst", ".adoc"},
                "INVALID_PROJECT_DOCUMENT", "Cite a project documentation file")
        raw, content = read_code(root, path)
        quote = text(ref.get("quote"), "quote", 2000)
        require(ref.get("file_sha256") == digest(raw) and quote in content,
                "PROJECT_QUOTE_MISMATCH", "Document version and exact quote must match the file")
        start = content[:content.index(quote)].count("\n") + 1
        result.append({"kind": "PROJECT_DOCUMENT", "path": path, "file_sha256": digest(raw), "quote": quote,
                       "start_line": start, "end_line": start + quote.count("\n"), "captured_at": now(),
                       "literal_reference_valid": True, "semantic_verified": False})
    return result
