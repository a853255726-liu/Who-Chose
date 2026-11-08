"""Bounded immutable start snapshots. Exclusions remain visible, not silently dropped."""
import difflib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import time
from itertools import islice

from .contracts import require, digest, SECRET

FILE_LIMIT = 256 * 1024
TOTAL_LIMIT = 20 * 1024 * 1024
COUNT_LIMIT = 2000
RETENTION_SECONDS = 7 * 24 * 3600
BLOB_LIMIT = 80 * 1024 * 1024
BLOB_COUNT_LIMIT = 10000
PRIVATE = {".git", ".codex", ".agents", ".aws", ".ssh", ".venv", "venv", "node_modules", "__pycache__",
           ".pytest_cache", ".whochose", ".buildchoice", "phase0", "work", "dist", "build"}
SECRET_NAMES = {"credentials", "credentials.json", "auth.json", "id_rsa", "id_ed25519"}


def normalize(path, allow_root=False):
    require(isinstance(path, str) and bool(path) and len(path) <= 512 and "\0" not in path and ":" not in path,
            "UNSAFE_PATH", "Expected a workspace-relative path")
    path = path.replace("\\", "/")
    p = PurePosixPath(path)
    require(not p.is_absolute() and ".." not in p.parts and all(not s.endswith((" ", ".")) for s in p.parts),
            "UNSAFE_PATH", "Path must stay inside the workspace")
    require(bool(p.parts) or allow_root, "UNSAFE_PATH", "Empty path")
    return p.as_posix()


def excluded(path):
    parts = PurePosixPath(path).parts
    if any(p.lower() in PRIVATE or p.startswith(".") for p in parts):
        return "private_or_generated_directory"
    if parts and (parts[-1].lower() in SECRET_NAMES or Path(parts[-1]).suffix.lower() in {".pem", ".key", ".pfx", ".sqlite3", ".db"}):
        return "sensitive_file"
    if parts and parts[-1] in {"whochose-review.html", "whochose-review.md"}:
        return "generated_review"
    return None


def safe_path(root, relative):
    relative = normalize(relative)
    require(not excluded(relative), "PRIVATE_PATH", "Private/generated paths are excluded")
    current = Path(root)
    for part in PurePosixPath(relative).parts:
        current /= part
        require(not current.is_symlink() and not (hasattr(current, "is_junction") and current.is_junction()),
                "LINKED_PATH", "Linked evidence paths are excluded")
    require(current.resolve().is_relative_to(Path(root).resolve()), "UNSAFE_PATH", "Path escapes workspace")
    return current


def read_code(root, relative):
    path = safe_path(root, relative)
    with path.open("rb") as stream:
        raw = stream.read(FILE_LIMIT + 1)
    require(len(raw) <= FILE_LIMIT, "FILE_TOO_LARGE", "File exceeds the 256 KiB evidence limit")
    require(b"\0" not in raw, "BINARY_FILE", "Binary files cannot be inspected")
    text = raw.decode("utf-8-sig")
    require(not SECRET.search(text), "SENSITIVE_CONTENT", "Credential-like content is excluded")
    return raw, text


def git_state(root):
    try:
        opts = dict(cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
                    env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}, stdin=subprocess.DEVNULL)
        result = subprocess.run(["git", "-c", "core.fsmonitor=false", "status", "--porcelain=v2", "--branch", "--", "."], **opts)
        if result.returncode:
            return {"available": False, "reason": "not_git_or_unavailable"}
        lines = result.stdout[:64000].splitlines()
        head = next((s.removeprefix("# branch.oid ") for s in lines if s.startswith("# branch.oid ")), None)
        return {"available": True, "head": None if head == "(initial)" else head,
                "dirty": any(not s.startswith("#") for s in lines), "status_truncated": len(result.stdout) > 64000}
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "reason": "git_unavailable"}


def capture(store, root, scopes):
    root = Path(root)
    found, visited, total = {}, set(), 0
    blob_paths = list(islice(store.blobs.iterdir(), BLOB_COUNT_LIMIT + 1))
    used = sum(p.stat().st_size for p in blob_paths if p.is_file() and not p.is_symlink())
    blob_count = len(blob_paths)
    pending = []
    for scope in scopes:
        scope = normalize(scope, allow_root=True)
        if any(c in scope for c in "*?[]"):
            # Older stored tasks may contain patterns; keep their gap visible.
            found[scope] = {"status": "unsupported_scope_pattern"}
            continue
        pending.append(root if scope == "." else root / scope)
    while pending:
        path = pending.pop()
        relative = path.relative_to(root).as_posix()
        if relative in visited:
            continue
        visited.add(relative)
        if len(visited) > COUNT_LIMIT:
            found[relative] = {"status": "traversal_limit"}
            found["<remaining>"] = {"status": "traversal_limit", "pending_count": len(pending)}
            break
        reason = excluded(relative)
        if reason:
            found[relative] = {"status": reason}
            continue
        try:
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                found[relative] = {"status": "linked_path"}
            elif path.is_dir():
                children = list(islice(path.iterdir(), COUNT_LIMIT + 1))
                if len(children) > COUNT_LIMIT:
                    found[relative + "/*"] = {"status": "traversal_limit"}
                pending.extend(sorted(children[:COUNT_LIMIT], reverse=True))
            elif not path.exists():
                found[relative] = {"status": "absent"}
            elif path.is_file():
                before = path.stat()
                raw, _ = read_code(root, relative)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    found[relative] = {"status": "changed_during_capture"}
                elif total + len(raw) > TOTAL_LIMIT:
                    found[relative] = {"status": "snapshot_quota"}
                else:
                    sha = digest(raw)
                    blob = store.blobs / sha
                    require(not blob.is_symlink(), "LINKED_PATH", "Snapshot blob must not be linked")
                    if not blob.exists():
                        if used + len(raw) > BLOB_LIMIT or blob_count >= BLOB_COUNT_LIMIT:
                            found[relative] = {"status": "store_quota"}
                            continue
                        blob.write_bytes(raw)
                        used += len(raw)
                        blob_count += 1
                    total += len(raw)
                    found[relative] = {"status": "captured", "sha256": sha, "bytes": len(raw)}
            else:
                found[relative] = {"status": "unsupported_file_type"}
        except Exception as exc:
            from .contracts import ContractError
            if not isinstance(exc, (OSError, UnicodeError, ContractError)):
                raise
            found[relative] = {"status": getattr(exc, "code", "unreadable")}
    return {"files": found, "captured_at": time.time(), "bytes": total, "git": git_state(root),
            "scopes": scopes, "outside_scope": "not_inspected", "kind": "bounded_start_snapshot"}


def baseline_state(baseline):
    partial = {"unsupported_scope_pattern", "traversal_limit", "changed_during_capture", "snapshot_quota", "store_quota", "unreadable"}
    return "PARTIAL_BASELINE" if any(e["status"] in partial for e in baseline["files"].values()) else "BOUNDED_BASELINE"


def blob_text(store, sha):
    require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha), "INVALID_VERSION", "Invalid blob version")
    path = store.blobs / sha
    require(not path.is_symlink(), "LINKED_PATH", "Snapshot blob is linked")
    raw = path.read_bytes()
    require(digest(raw) == sha, "BLOB_CHANGED", "Snapshot bytes do not match their stored version")
    return raw.decode("utf-8-sig")


def diff_chunks(store, before_sha, after_sha, old_text, new_text):
    """Prefer actual Git's diff algorithm; identical fallback when Git is unavailable."""
    backend = "difflib"
    patch = ""
    if before_sha and after_sha:
        try:
            result = subprocess.run(["git", "--no-pager", "diff", "--no-index", "--no-ext-diff", "--text", "--unified=3", "--",
                str(store.blobs / before_sha), str(store.blobs / after_sha)], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=5, stdin=subprocess.DEVNULL,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"})
            if result.returncode in (0, 1):
                patch, backend = result.stdout, "git_no_index"
        except (OSError, subprocess.TimeoutExpired):
            pass
    if not patch:
        patch = "".join(difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True), fromfile="before", tofile="after"))
    lines = patch.splitlines(True)
    chunks, current = [], None
    for line in lines:
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if match:
            if current:
                chunks.append(current)
            current = {"old_start": int(match[1]), "old_count": int(match[2] or 1),
                       "new_start": int(match[3]), "new_count": int(match[4] or 1), "patch": line, "diff_backend": backend}
        elif current:
            current["patch"] += line
    if current:
        chunks.append(current)
    if not chunks:
        chunks = [{"old_start": 0, "old_count": len(old_text.splitlines()), "new_start": 0,
                   "new_count": len(new_text.splitlines()), "patch": "", "diff_backend": backend}]
    for chunk in chunks:
        chunk["patch_truncated"] = len(chunk["patch"]) > 8000
        chunk["patch"] = chunk["patch"][:8000]
    return chunks


def refresh(store, task_id, refresh_now=True):
    from .contracts import encode, ContractError
    with store.connect() as db:
        task = store.task(db, task_id)
    if task["status"] != "OPEN" and task.get("end_snapshot"):
        return {**json.loads(task["end_snapshot"]), "frozen_at_completion": True}
    if not refresh_now and task.get("last_scan"):
        return {**json.loads(task["last_scan"]), "cached": True}
    before = json.loads(task["baseline"])
    after = capture(store, task["workspace_root"], json.loads(task["scope"]))
    old, new = before["files"], after["files"]
    uninspected, exclusions, hunks = [], [], []
    expired = time.time() - before["captured_at"] > RETENTION_SECONDS
    removed = {p: e for p, e in old.items() if e["status"] == "captured" and (p not in new or new[p]["status"] == "absent")}
    added = {p: e for p, e in new.items() if e["status"] == "captured" and (p not in old or old[p]["status"] == "absent")}
    renames = {}
    for path, entry in removed.items():
        matches = [p for p, e in added.items() if e["sha256"] == entry["sha256"]]
        if len(matches) == 1 and sum(e["sha256"] == entry["sha256"] for e in removed.values()) == 1:
            renames[path] = matches[0]
    consumed = set(renames.values())
    for path in sorted(set(old) | set(new)):
        if path in consumed:
            continue
        a, b = old.get(path, {"status": "absent"}), new.get(path, {"status": "absent"})
        renamed = path in renames
        target = renames.get(path, path)
        if renamed:
            b = new[target]
        if a["status"] not in {"captured", "absent"} or b["status"] not in {"captured", "absent"}:
            target_list = exclusions if {a["status"], b["status"]} <= {"absent", "private_or_generated_directory", "sensitive_file", "generated_review"} else uninspected
            target_list.append({"path": path, "before": a["status"], "after": b["status"]})
            continue
        if a.get("sha256") == b.get("sha256") and not renamed:
            continue
        if expired:
            uninspected.append({"path": path, "reason": "baseline_expired"})
            continue
        try:
            left = blob_text(store, a["sha256"]) if a.get("sha256") else ""
            right = blob_text(store, b["sha256"]) if b.get("sha256") else ""
            chunks = diff_chunks(store, a.get("sha256"), b.get("sha256"), left, right)
        except (OSError, UnicodeError, ContractError):
            uninspected.append({"path": path, "reason": "snapshot_content_unavailable"})
            continue
        for chunk in chunks:
            base = {"path": target, "old_path": path if renamed else None,
                    "kind": "renamed" if renamed else "added" if a["status"] == "absent" else "deleted" if b["status"] == "absent" else "modified",
                    "before_sha256": a.get("sha256"), "after_sha256": b.get("sha256"), **chunk}
            hunk_id = "hunk-" + digest(encode({"task": task_id, **{k: v for k, v in base.items() if k not in {"patch", "diff_backend", "patch_truncated"}}}))[:32]
            hunks.append({"hunk_id": hunk_id, **base})
    generation = digest(encode({"hunks": [h["hunk_id"] for h in hunks], "uninspected": uninspected}))
    result = {"task_id": task_id, "generation": generation, "hunks": hunks, "uninspected": uninspected, "exclusions": exclusions,
            "scope": json.loads(task["scope"]), "outside_scope": "not_inspected", "baseline_expired": expired,
            "baseline_state": "PARTIAL_BASELINE" if expired or baseline_state(after) == "PARTIAL_BASELINE" else task["baseline_state"], "git": after["git"],
            "rename_detection": "exact_content_only; edited moves remain delete/add", "semantic_coverage_verified": False}
    with store.transaction() as db:
        db.execute("UPDATE change_hunks SET active=0 WHERE task_id=?", (task_id,))
        for hunk in hunks:
            db.execute("INSERT INTO change_hunks VALUES(?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET active=1", (hunk["hunk_id"], task_id, hunk["path"], encode(hunk)))
        if expired or baseline_state(after) == "PARTIAL_BASELINE":
            db.execute("UPDATE tasks SET baseline_state='PARTIAL_BASELINE' WHERE id=?", (task_id,))
        db.execute("UPDATE tasks SET last_scan=? WHERE id=?", (encode(result), task_id))
    return result


def coverage(store, task_id, refresh_now=True):
    result = refresh(store, task_id) if refresh_now else None
    if result is None:
        return coverage(store, task_id, True)
    if result.get("frozen_at_completion"):
        return result
    states, source_conflicts = {}, []
    with store.connect() as db:
        task = store.task(db, task_id)
        for hunk in result["hunks"]:
            links = db.execute("SELECT * FROM hunk_links WHERE hunk_id=?", (hunk["hunk_id"],)).fetchall()
            valid = []
            for link in links:
                if link["classification"] == "DECISION_LINKED":
                    row = db.execute("SELECT revision FROM decisions WHERE id=?", (link["record_id"],)).fetchone()
                    if row and row["revision"] == link["revision"]:
                        valid.append(link["classification"])
                elif db.execute("SELECT 1 FROM ordinary_changes WHERE id=? AND task_id=?", (link["record_id"], task_id)).fetchone():
                    valid.append(link["classification"])
            states[hunk["hunk_id"]] = next((s for s in ("DECISION_LINKED", "ORDINARY_EXPLAINED", "EXCLUDED_WITH_REASON") if s in valid), "UNREVIEWED")
        for row in db.execute("SELECT r.decision_id,r.data FROM decision_revisions r JOIN decisions d ON d.id=r.decision_id AND d.revision=r.revision WHERE r.task_id=?", (task_id,)):
            data = json.loads(row["data"])
            if data["source_class"] == "USER_SPECIFIED":
                for ref in data["source_evidence_refs"]:
                    if data.get("user_confirmation") == "PROJECT_DOCUMENT":
                        for document in ref.get("source_evidence_refs", []):
                            try:
                                raw, _ = read_code(task["workspace_root"], document["path"])
                                current = digest(raw) == document["file_sha256"]
                            except (OSError, UnicodeError, ValueError):
                                current = False
                            if not current:
                                source_conflicts.append({"record_id": row["decision_id"], "reason": "project_document_changed",
                                                         "path": document["path"]})
                    latest = db.execute("SELECT max(revision) FROM user_decisions WHERE id=?", (ref["record_id"],)).fetchone()[0]
                    if latest != ref["revision"]:
                        source_conflicts.append({"record_id": row["decision_id"], "reason": "user_decision_revised", "user_record_id": ref["record_id"]})
    counts = {s: sum(v == s for v in states.values()) for s in ("DECISION_LINKED", "ORDINARY_EXPLAINED", "EXCLUDED_WITH_REASON", "UNREVIEWED")}
    return {**result, "coverage": states, "counts": counts, "source_conflicts": source_conflicts, "unreviewed_hunk_refs": [h for h, state in states.items() if state == "UNREVIEWED"],
            "complete_within_inspected_scope": not counts["UNREVIEWED"] and not result["uninspected"] and not source_conflicts and result["baseline_state"] != "PARTIAL_BASELINE"}
