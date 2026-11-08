"""SQLite is the only authoritative state; blobs are content-addressed evidence."""
import json
import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager

from .contracts import require, now, digest, encode

SCHEMA_VERSION = 2
SCHEMA = """
CREATE TABLE workspaces(id TEXT PRIMARY KEY, root TEXT NOT NULL UNIQUE);
CREATE TABLE tasks(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 start_key TEXT NOT NULL, scope TEXT NOT NULL, description TEXT NOT NULL, task_revision INTEGER NOT NULL,
 status TEXT NOT NULL, created TEXT NOT NULL, completed TEXT, baseline TEXT NOT NULL, baseline_state TEXT NOT NULL,
 end_snapshot TEXT, last_scan TEXT,
 UNIQUE(workspace_id,start_key));
CREATE TABLE hook_messages(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 session_id TEXT NOT NULL, turn_id TEXT NOT NULL, digest TEXT NOT NULL, excerpt TEXT NOT NULL,
 length INTEGER NOT NULL, captured_at TEXT NOT NULL, transport TEXT NOT NULL,
 UNIQUE(workspace_id,session_id,turn_id));
CREATE TABLE hook_state(workspace_id TEXT NOT NULL, session_id TEXT NOT NULL, task_id TEXT REFERENCES tasks(id),
 turn_id TEXT, dirty INTEGER NOT NULL DEFAULT 0, nudge_count INTEGER NOT NULL DEFAULT 0,
 last_recorded_change_id TEXT, last_nudge_change_id TEXT, last_tool_nudge REAL NOT NULL DEFAULT 0,
 PRIMARY KEY(workspace_id,session_id));
CREATE TABLE user_decisions(id TEXT NOT NULL, revision INTEGER NOT NULL, task_id TEXT NOT NULL REFERENCES tasks(id),
 workspace_id TEXT NOT NULL REFERENCES workspaces(id), behavior_key TEXT NOT NULL, data TEXT NOT NULL,
 created TEXT NOT NULL, PRIMARY KEY(id,revision));
CREATE TABLE operations(task_id TEXT NOT NULL REFERENCES tasks(id), operation TEXT NOT NULL, key TEXT NOT NULL,
 input_digest TEXT NOT NULL, result TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(task_id,operation,key));
CREATE TABLE functional_blocks(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
 block_key TEXT NOT NULL, name TEXT NOT NULL, UNIQUE(task_id,block_key));
CREATE TABLE decisions(id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 behavior_key TEXT NOT NULL, revision INTEGER NOT NULL, UNIQUE(workspace_id,behavior_key));
CREATE TABLE decision_revisions(decision_id TEXT NOT NULL REFERENCES decisions(id), revision INTEGER NOT NULL,
 task_id TEXT NOT NULL REFERENCES tasks(id), block_id TEXT NOT NULL REFERENCES functional_blocks(id),
 data TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(decision_id,revision));
CREATE TABLE ordinary_changes(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
 block_id TEXT NOT NULL REFERENCES functional_blocks(id), data TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE evidence_refs(id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id), kind TEXT NOT NULL,
 data TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE code_links(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
 record_id TEXT NOT NULL, revision INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE change_hunks(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
 path TEXT NOT NULL, data TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE hunk_links(hunk_id TEXT NOT NULL REFERENCES change_hunks(id), record_id TEXT NOT NULL,
 revision INTEGER NOT NULL, classification TEXT NOT NULL, reason TEXT,
 PRIMARY KEY(hunk_id,record_id,revision));
CREATE INDEX user_task ON user_decisions(task_id);
CREATE INDEX user_behavior ON user_decisions(workspace_id,behavior_key);
CREATE INDEX revision_task ON decision_revisions(task_id);
CREATE INDEX hunk_task ON change_hunks(task_id,active);
CREATE INDEX code_record ON code_links(record_id,revision);
"""


def default_data_root():
    if os.environ.get("WHOCHOSE_DATA"):
        return Path(os.environ["WHOCHOSE_DATA"]).expanduser()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "WhoChose"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "whochose"


class Store:
    def __init__(self, data_root=None):
        self.root = Path(data_root or default_data_root()).absolute()
        for ancestor in [self.root, *self.root.parents]:
            require(not ancestor.is_symlink() and not (hasattr(ancestor, "is_junction") and ancestor.is_junction()),
                    "UNSAFE_DATA_PATH", "Data directory must not traverse links")
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve()
        self.database = self.root / "whochose.sqlite3"
        require(not self.database.is_symlink(), "LINKED_PATH", "Database must not be a linked file")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            require(version <= SCHEMA_VERSION, "SCHEMA_TOO_NEW", "Database was created by a newer WhoChose")
            if version == 0:
                for statement in SCHEMA.split(";"):
                    if statement.strip():
                        db.execute(statement)
                db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            elif version == 1:
                db.execute("ALTER TABLE tasks ADD COLUMN end_snapshot TEXT")
                db.execute("ALTER TABLE tasks ADD COLUMN last_scan TEXT")
                db.execute("PRAGMA user_version=2")
        self.blobs = self.root / "blobs"
        require(not self.blobs.is_symlink() and not (hasattr(self.blobs, "is_junction") and self.blobs.is_junction()),
                "LINKED_PATH", "Blob directory must not be linked")
        self.blobs.mkdir(exist_ok=True)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    def workspace(self, db, root):
        root = Path(root).resolve(strict=True)
        require(root.is_dir(), "INVALID_WORKSPACE", "Workspace must be a directory")
        require(not self.root.is_relative_to(root), "DATA_INSIDE_WORKSPACE", "Store data outside the code workspace")
        normalized = os.path.normcase(str(root))
        workspace_id = digest(normalized)[:24]
        db.execute("INSERT OR IGNORE INTO workspaces VALUES(?,?)", (workspace_id, str(root)))
        return workspace_id, root

    def task(self, db, task_id):
        row = db.execute("SELECT t.*,w.root workspace_root FROM tasks t JOIN workspaces w ON w.id=t.workspace_id WHERE t.id=?", (task_id,)).fetchone()
        require(row is not None, "TASK_NOT_FOUND", "Unknown task_id")
        return dict(row)

    def replay(self, db, task_id, operation, key, payload):
        from .contracts import text
        text(key, "idempotency_key", 200)
        fingerprint = digest(encode(payload))
        old = db.execute("SELECT * FROM operations WHERE task_id=? AND operation=? AND key=?", (task_id, operation, key)).fetchone()
        if old:
            require(old["input_digest"] == fingerprint, "IDEMPOTENCY_CONFLICT", "Key was already used with different content")
            return {**json.loads(old["result"]), "replayed": True}, fingerprint
        return None, fingerprint

    def remember(self, db, task_id, operation, key, fingerprint, result):
        db.execute("INSERT INTO operations VALUES(?,?,?,?,?,?)", (task_id, operation, key, fingerprint, encode(result), now()))
