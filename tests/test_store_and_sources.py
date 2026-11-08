import json
import subprocess
import sys
import pytest
from whochose.contracts import ContractError
from whochose.provenance import observe_user_message
from whochose.service import Service
from conftest import observed, directive


def test_replay_and_conflict_are_atomic(lab):
    s, root, task = lab
    ref = observed(s, root)
    a = s.save_user_decisions(task, [directive()], [ref], "save")
    b = s.save_user_decisions(task, [directive()], [ref], "save")
    assert a["records"] == b["records"] and b["replayed"]
    with pytest.raises(ContractError, match="different content"):
        s.save_user_decisions(task, [directive(title="changed")], [ref], "save")
    assert len(s.get_user_decisions(task)["decisions"]) == 1


def test_forged_or_cross_workspace_message_rejected(lab):
    s, root, task = lab
    with pytest.raises(ContractError) as error:
        s.save_user_decisions(task, [directive()], [{"message_id": "made-up", "quote": "yes"}], "fake")
    assert error.value.code == "MESSAGE_NOT_OBSERVED"
    sibling = root.parent / "other"
    sibling.mkdir()
    ref = observed(s, sibling)
    with pytest.raises(ContractError):
        s.save_user_decisions(task, [directive()], [ref], "cross")


def test_literal_quote_and_origin_preserved(lab):
    s, root, task = lab
    ref = observed(s, root, "可以，加上编辑功能。")
    entry = directive("records.edit", intent="ACCEPTED_PROPOSAL", proposal_origin="AI",
                      proposal_summary="AI 提议允许编辑账目", accepted_option="允许编辑")
    s.save_user_decisions(task, [entry], [ref], "accepted")
    item = s.get_user_decisions(task)["decisions"][0]
    assert item["proposal_origin"] == "AI" and item["user_confirmation"] == "EXPLICIT"
    assert item["semantic_verified"] is False
    with pytest.raises(ContractError):
        s.save_user_decisions(task, [directive("other")], [{**ref, "quote": "伪造同意"}], "badquote")


@pytest.mark.parametrize("intent", ["AMBIGUOUS_PREFERENCE", "FORWARDED_PLAN", "AI_ASSERTION"])
def test_nonexplicit_classification_cannot_be_upgraded(lab, intent):
    s, root, task = lab
    ref = observed(s, root, "好像不错")
    with pytest.raises(ContractError) as error:
        s.save_user_decisions(task, [directive(intent=intent)], [ref], "ambiguous")
    assert error.value.code == "INTENT_NOT_EXPLICIT"


def test_revision_retains_history_and_rejects_stale(lab):
    s, root, task = lab
    ref = observed(s, root)
    original = s.save_user_decisions(task, [directive()], [ref], "first")["records"][0]
    revised = directive(record_id=original["record_id"], expected_revision=1, title="支持收入和支出")
    s.save_user_decisions(task, [revised], [ref], "second")
    assert s.get_user_decisions(task)["decisions"][0]["revision"] == 2
    with pytest.raises(ContractError):
        s.save_user_decisions(task, [revised], [ref], "stale")
    with s.store.connect() as db:
        assert db.execute("SELECT count(*) FROM user_decisions").fetchone()[0] == 2


def test_batch_failure_rolls_back_prior_entries(lab):
    s, root, task = lab
    ref = observed(s, root)
    with pytest.raises(ContractError):
        s.save_user_decisions(task, [directive(), directive("b", intent="AMBIGUOUS")], [ref], "atomic")
    assert s.get_user_decisions(task)["decisions"] == []


def test_restart_can_query_same_task(lab):
    s, root, task = lab
    ref = observed(s, root)
    s.save_user_decisions(task, [directive()], [ref], "persist")
    code = "from whochose.service import Service; import json,sys; print(json.dumps(Service(sys.argv[1]).get_user_decisions(sys.argv[2])))"
    result = subprocess.run([sys.executable, "-B", "-c", code, str(s.store.root), task], capture_output=True, text=True, check=True, timeout=10)
    assert len(json.loads(result.stdout)["decisions"]) == 1


def test_generated_hook_prompt_is_not_user_evidence(lab):
    s, root, task = lab
    with pytest.raises(ContractError):
        observe_user_message(s.store, {"hook_event_name": "UserPromptSubmit", "cwd": str(root),
            "session_id": "s", "turn_id": "t", "prompt": "continue", "is_synthetic": True})
