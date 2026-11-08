"""Bounded retries for SQLite lock contention, with non-sensitive diagnostics."""
from functools import wraps
import sqlite3
import time


RETRY_DELAYS = (0.05, 0.15)


def sqlite_code(error):
    # Extended codes such as SQLITE_BUSY_SNAPSHOT share the low-byte base code.
    return getattr(error, "sqlite_errorcode", 0) & 255


def retry_busy(method):
    """Retry whole idempotent service calls, after their transaction unwinds."""
    @wraps(method)
    def call(*args, **kwargs):
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                return method(*args, **kwargs)
            except sqlite3.Error as error:
                error.whochose_attempts = attempt + 1
                if sqlite_code(error) not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED} or attempt == len(RETRY_DELAYS):
                    raise
                time.sleep(RETRY_DELAYS[attempt])
    return call


def storage_error_result(error):
    code = sqlite_code(error)
    retryable = code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
    if retryable:
        label, message = "STORAGE_BUSY", "Database is temporarily locked; retry the identical request with the same idempotency key"
    elif code == sqlite3.SQLITE_CONSTRAINT:
        label, message = "STORAGE_CONSTRAINT", "Database constraint failed; repeating this request will not repair it"
    elif code in {sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB}:
        label, message = "STORAGE_CORRUPT", "Database integrity error; stop writes and inspect a backup"
    elif code in {sqlite3.SQLITE_IOERR, sqlite3.SQLITE_CANTOPEN, sqlite3.SQLITE_READONLY, sqlite3.SQLITE_FULL}:
        label, message = "STORAGE_IO_ERROR", "Database access failed; check permissions, availability and free space"
    else:
        label, message = "STORAGE_ERROR", "Database operation failed; inspect the SQLite error code before retrying"
    # Never expose SQLite's raw message: it can contain SQL, paths or user data.
    return {"ok": False, "error": {"code": label, "message": message,
        "sqlite_errorname": getattr(error, "sqlite_errorname", "UNKNOWN"),
        "sqlite_errorcode": getattr(error, "sqlite_errorcode", None),
        "retryable": retryable, "attempts": getattr(error, "whochose_attempts", 1)}}
