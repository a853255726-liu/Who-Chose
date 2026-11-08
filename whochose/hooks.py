"""Trusted local command entry, separate from the public MCP tools.

Trust boundary: locally reviewed host callbacks; not secure against arbitrary
same-user processes capable of modifying this SQLite database.
"""
import json
import sys
import os
import time
from pathlib import Path
from .contracts import digest, encode
from .storage import Store
from .provenance import observe_user_message


def handle(event, data_root=None):
    name = event.get("hook_event_name")
    if name == "UserPromptSubmit":
        ref = observe_user_message(Store(data_root), event)
        context = {"whochose_message_ref": ref, "session_id": event["session_id"],
                   "instruction": "Before editing start/resume the scoped WhoChose task. Use capture-decisions only for clear actual user instructions; do not infer approval from this receipt."}
        return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": json.dumps(context, ensure_ascii=False)}}
    # A turn may end while waiting for a user; delivery is explicit complete.
    if name == "Stop":
        return {}
    if name != "PostToolUse":
        return {}
    store = Store(data_root)
    wid = digest(os.path.normcase(str(Path(event["cwd"]).resolve())))[:24]
    session = event.get("session_id")
    with store.connect() as db:
        state = db.execute("SELECT * FROM hook_state WHERE workspace_id=? AND session_id=?", (wid, session)).fetchone()
        state = dict(state) if state else None
    if not state:
        return {}
    if name == "PostToolUse":
        tool = event.get("tool_name", "")
        if tool.startswith("mcp__whochose__") or tool in {"read_mcp_resource", "list_mcp_resources", "list_mcp_resource_templates", "view_image"}:
            return {}
        supported = tool in {"Bash", "exec_command", "apply_patch", "Edit", "Write", "functions.exec", "functions.exec_command"} or tool.startswith("mcp__")
        if not supported:
            return {}
        if state["task_id"]:
            with store.connect() as db:
                if store.task(db, state["task_id"])["status"] != "OPEN":
                    return {}
            from .changes import coverage
            checked = coverage(store, state["task_id"])
            pending = bool(checked["counts"]["UNREVIEWED"] or checked["uninspected"] or checked["source_conflicts"])
            nudge = bool(checked["counts"]["UNREVIEWED"]) and time.time() - state["last_tool_nudge"] >= 20
            with store.transaction() as db:
                db.execute("UPDATE hook_state SET dirty=?,turn_id=?,last_recorded_change_id=?,last_tool_nudge=? WHERE workspace_id=? AND session_id=?",
                           (int(pending), event.get("turn_id"), checked["generation"],
                            time.time() if nudge else state["last_tool_nudge"], wid, session))
            if not nudge:
                return {}
            return {"hookSpecificOutput": {"hookEventName": name, "additionalContext":
                    "WhoChose: 当前范围有未记录的真实变化；在适当批次记录，任务交付前显式 complete。等待用户回答时可直接结束本轮。"}}
        # Without a bound baseline, a tool name alone cannot prove read-only use.
        nudge = time.time() - state["last_tool_nudge"] >= 20
        with store.transaction() as db:
            db.execute("UPDATE hook_state SET dirty=1,turn_id=?,last_tool_nudge=? WHERE workspace_id=? AND session_id=?",
                       (event.get("turn_id"), time.time() if nudge else state["last_tool_nudge"], wid, session))
        if not nudge:
            return {}
        hint = ("WhoChose: 在适当批次使用 trace-implementation 记录真实重要选择及普通调整；完成前检查 diff 覆盖。"
                if state["task_id"] else "WhoChose: 已观察到可能修改工作区的工具，但未绑定任务。现在开始只能保留 PARTIAL_BASELINE，不得声称覆盖此前改动。")
        return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": hint}}
    return {}


def main():
    try:
        raw = sys.stdin.buffer.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            raise ValueError("Hook input exceeds 128 KiB")
        event = json.loads(raw.decode("utf-8-sig"))
        result = handle(event)
    except Exception:
        # Hook failure must never swallow a development tool's output or block a task.
        result = {"systemMessage": "WhoChose 本次 Hook 未完成；自动观察有缺口，请显式执行任务完成检查。"}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
