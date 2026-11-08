from pathlib import Path
import uuid
import pytest
from whochose.service import Service
from whochose.provenance import observe_user_message


@pytest.fixture
def lab():
    base = Path(__file__).resolve().parents[1] / "work" / "tests" / uuid.uuid4().hex
    workspace = base / "中文 空格代码"
    workspace.mkdir(parents=True)
    service = Service(base / "data")
    task = service.get_task_context(str(workspace), "start", idempotency_key="start")
    return service, workspace, task["task_id"]


def observed(service, workspace, prompt="支持记录支出", turn="turn-1", session="session-1"):
    ref = observe_user_message(service.store, {"hook_event_name": "UserPromptSubmit", "cwd": str(workspace),
        "session_id": session, "turn_id": turn, "prompt": prompt})
    return {**ref, "quote": prompt}


def directive(behavior="records.add", **extra):
    return {"behavior_key": behavior, "title": "支持新增支出记录", "intent": "DIRECT_INSTRUCTION",
            "proposal_origin": "USER", **extra}
