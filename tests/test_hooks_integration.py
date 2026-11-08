import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from whochose.hooks import handle
from whochose.contracts import ContractError
from conftest import directive


def test_hook_process_to_message_to_saved_decision(lab):
    s, root, task = lab
    event = {"hook_event_name": "UserPromptSubmit", "cwd": str(root), "session_id": "s", "turn_id": "t", "prompt": "支持记录支出"}
    result = subprocess.run([sys.executable, "-B", "-m", "whochose.hooks"], input=json.dumps(event), text=True,
        encoding="utf-8", capture_output=True, check=True, timeout=10,
        env={**os.environ, "WHOCHOSE_DATA": str(s.store.root), "PYTHONUTF8": "1"})
    ctx = json.loads(json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"])
    assert "session_id" in ctx
    bound = s.get_task_context(str(root), "resume", task_id=task, session_id="s")
    ref = {**ctx["whochose_message_ref"], "quote": event["prompt"]}
    s.save_user_decisions(task, [directive()], [ref], "hook-to-store")
    assert s.get_user_decisions(task)["decisions"][0]["source_evidence_refs"][0]["message_id"] == ref["message_id"]
    assert bound["user_message_refs"][0]["message_id"] == ref["message_id"]


def test_hook_failure_is_nonblocking_and_observable(lab):
    s, root, _ = lab
    result = subprocess.run([sys.executable, "-B", "-m", "whochose.hooks"], input="{bad json", text=True,
        capture_output=True, encoding="utf-8", env={**os.environ, "WHOCHOSE_DATA": str(s.store.root), "PYTHONUTF8": "1"}, timeout=5)
    assert result.returncode == 0 and "systemMessage" in json.loads(result.stdout)


def test_long_message_does_not_store_entire_conversation(lab):
    s, root, _ = lab
    out = handle({"hook_event_name": "UserPromptSubmit", "cwd": str(root), "session_id": "long", "turn_id": "t",
                  "prompt": "a" * 5000}, s.store.root)
    ref = json.loads(out["hookSpecificOutput"]["additionalContext"])["whochose_message_ref"]
    assert ref["excerpt_truncated"]
    with s.store.connect() as db:
        assert len(db.execute("SELECT excerpt FROM hook_messages WHERE id=?", (ref["message_id"],)).fetchone()[0]) == 4000


def native_reply(answer="仍要保存", call="call_test"):
    item = {"questionItemId": json.dumps(["request_user_input_async", call, 0]),
            "question": "疑似重复时怎样处理？", "answer": answer}
    return "<send_user_message_question_reply>\n" + json.dumps([item], ensure_ascii=False) + "\n</send_user_message_question_reply>"


def test_native_reply_in_same_turn_can_save_user_acceptance_and_replay(lab):
    s, root, task = lab
    event = {"hook_event_name": "UserPromptSubmit", "cwd": str(root),
             "session_id": "native", "turn_id": "same-turn", "prompt": "解决重复录入"}

    def submit(prompt):
        result = subprocess.run([sys.executable, "-B", "-m", "whochose.hooks"],
            input=json.dumps({**event, "prompt": prompt}), text=True, encoding="utf-8",
            capture_output=True, check=True, timeout=10,
            env={**os.environ, "WHOCHOSE_DATA": str(s.store.root), "PYTHONUTF8": "1"})
        output = json.loads(result.stdout)
        assert "hookSpecificOutput" in output, output
        return json.loads(output["hookSpecificOutput"]["additionalContext"])["whochose_message_ref"]

    original = submit(event["prompt"])
    reply = native_reply()
    ref = submit(reply)
    assert ref["message_id"] != original["message_id"]
    assert submit(reply) == ref
    assert submit(event["prompt"]) == original
    bound = s.get_task_context(str(root), "resume", task_id=task, session_id="native")
    assert {r["message_id"] for r in bound["user_message_refs"]} == {original["message_id"], ref["message_id"]}
    entry = directive("duplicates.prompt", intent="ACCEPTED_PROPOSAL", proposal_origin="AI",
                      proposal_summary="疑似重复时提醒并默认取消", accepted_option="仍要保存")
    s.save_user_decisions(task, [entry], [{**ref, "quote": "仍要保存"}], "native-acceptance")
    saved = s.get_user_decisions(task)["decisions"][0]
    assert saved["proposal_origin"] == "AI" and saved["user_confirmation"] == "EXPLICIT"
    assert saved["source_evidence_refs"][0]["message_id"] == ref["message_id"]
    assert saved["semantic_verified"] is False


def test_native_reply_keeps_card_identity_and_rejects_rewritten_answer(lab):
    s, root, _ = lab
    event = {"hook_event_name": "UserPromptSubmit", "cwd": str(root),
             "session_id": "native", "turn_id": "same-turn"}
    def submit(prompt):
        out = handle({**event, "prompt": prompt}, s.store.root)
        return json.loads(out["hookSpecificOutput"]["additionalContext"])["whochose_message_ref"]
    original = submit("原请求")
    first = submit(native_reply())
    second = submit(native_reply(call="call_second"))
    assert len({r["message_id"] for r in (original, first, second)}) == 3
    with pytest.raises(ContractError) as error:
        submit(native_reply(answer="取消"))
    assert error.value.code == "HOST_TURN_REUSED"
    assert submit(native_reply()) == first
    with s.store.connect() as db:
        assert db.execute("SELECT count(*) FROM hook_messages WHERE session_id='native'").fetchone()[0] == 3


@pytest.mark.parametrize("changed", [
    "普通消息改写",
    "<send_user_message_question_reply>not json</send_user_message_question_reply>",
    "<send_user_message_question_reply>[]</send_user_message_question_reply>",
    '<send_user_message_question_reply>[{"questionItemId":"unbound","question":"Q","answer":"A"}]</send_user_message_question_reply>',
])
def test_same_turn_ordinary_or_malformed_input_still_rejected(lab, changed):
    s, root, _ = lab
    event = {"hook_event_name": "UserPromptSubmit", "cwd": str(root),
             "session_id": "s", "turn_id": "same-turn", "prompt": "原请求"}
    handle(event, s.store.root)
    with pytest.raises(ContractError) as error:
        handle({**event, "prompt": changed}, s.store.root)
    assert error.value.code == "HOST_TURN_REUSED"
