"""Small explicit wire contracts. Literal validation does not verify semantics."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

TOOLS = ("get_task_context", "get_user_decisions", "save_user_decisions",
         "save_implementation_choices", "get_task_changes", "check_change_coverage", "get_review_report")
SOURCE_CLASSES = {"USER_SPECIFIED", "AI_SUPPLEMENTED", "UNKNOWN"}


class ContractError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def require(condition, code, message):
    if not condition:
        raise ContractError(code, message)


def now():
    return datetime.now(timezone.utc).isoformat()


def ident(prefix):
    return prefix + "-" + uuid.uuid4().hex


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()


def text(value, field, limit=2000):
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= limit,
            "INVALID_INPUT", f"{field} must be nonempty text of at most {limit} characters")
    return value


def entries(value):
    require(isinstance(value, list) and 0 < len(value) <= 100, "INVALID_INPUT", "Supply 1–100 entries")
    require(all(isinstance(e, dict) for e in value), "INVALID_INPUT", "Each entry must be an object")
    require(len(encode(value).encode()) <= 256 * 1024, "INPUT_TOO_LARGE", "Batch exceeds 256 KiB")
    return value


SECRET = re.compile(r'''(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|password|secret)["']?\s*[=:]\s*["']?[^\s"']+|-----BEGIN\s+(?:\w+\s+)?PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{16,}|\bgh[pousr]_[A-Za-z0-9]{20,}''')


def public_text(value):
    """Conservative export redaction, including bounded source/rationale excerpts."""
    return SECRET.sub("[已隐藏敏感内容]", str(value))
