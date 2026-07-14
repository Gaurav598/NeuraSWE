from app.agent.prompt_builder import PromptBuilder
from app.agent.trajectory import Trajectory
from app.tools.registry import build_default_registry


def test_system_prompt_examples_use_valid_json_object_syntax():
    prompt = PromptBuilder(build_default_registry()).system_prompt()

    assert '{{"tool":' not in prompt
    assert '"search_code": {{"query"' not in prompt
    assert 'ACTION: {"tool": "<tool_name>", "args": { ... }}' in prompt


def test_user_prompt_reports_failed_baseline_as_blocked_not_zero_failing():
    prompt = PromptBuilder(build_default_registry()).user_prompt(
        issue_block="GITHUB ISSUE\nTitle: x",
        trajectory=Trajectory(),
        baseline={"passed": "?", "failed": "?", "success": False, "exit_code": 1},
    )

    assert "BASELINE TESTS: failing/blocked before changes" in prompt
    assert "failed: ?" in prompt
    assert "0 failing" not in prompt
