"""Tests for the LLM response parser — the format robustness is critical."""

from app.agent.response_parser import parse_response


def test_clean_thought_and_action():
    text = (
        'THOUGHT: I should search for the login handler.\n'
        'ACTION: {"tool": "search_code", "args": {"query": "login handler"}}'
    )
    parsed = parse_response(text)
    assert parsed.action is not None
    assert parsed.action.tool == "search_code"
    assert parsed.action.args["query"] == "login handler"
    assert "login handler" in parsed.thought


def test_action_in_json_fence():
    text = (
        "THOUGHT: Let me read the file.\n"
        "ACTION:\n```json\n"
        '{"tool": "read_file", "args": {"path": "src/app.py"}}\n```'
    )
    parsed = parse_response(text)
    assert parsed.action.tool == "read_file"
    assert parsed.action.args["path"] == "src/app.py"


def test_action_with_trailing_prose():
    text = (
        'THOUGHT: Run tests now.\n'
        'ACTION: {"tool": "run_tests", "args": {}} '
        "and then I will review the output."
    )
    parsed = parse_response(text)
    assert parsed.action.tool == "run_tests"
    assert parsed.action.args == {}


def test_multiline_thought():
    text = (
        "THOUGHT: The bug is in the regex.\n"
        "It does not allow + characters.\n"
        'ACTION: {"tool": "grep", "args": {"pattern": "validateEmail"}}'
    )
    parsed = parse_response(text)
    assert "regex" in parsed.thought
    assert parsed.action.tool == "grep"


def test_single_quoted_json_recovered():
    text = "THOUGHT: x\nACTION: {'tool': 'git_diff', 'args': {}}"
    parsed = parse_response(text)
    assert parsed.action is not None
    assert parsed.action.tool == "git_diff"


def test_arguments_alias():
    text = 'THOUGHT: x\nACTION: {"name": "list_directory", "arguments": {"path": "."}}'
    parsed = parse_response(text)
    assert parsed.action.tool == "list_directory"
    assert parsed.action.args["path"] == "."


def test_no_action_returns_error():
    parsed = parse_response("THOUGHT: I am thinking but produced no action.")
    assert parsed.action is None
    assert parsed.parse_error is not None


def test_nested_braces_in_args():
    text = 'THOUGHT: edit\nACTION: {"tool": "edit_file", "args": {"path": "a.ts", "new_text": "if (x) { y(); }"}}'
    parsed = parse_response(text)
    assert parsed.action.tool == "edit_file"
    assert "{ y(); }" in parsed.action.args["new_text"]


def test_template_style_double_braces_recovered():
    text = (
        "THOUGHT: Search for the env var.\n"
        'ACTION: {{"tool": "search_code", "args": {{"query": "process.env.REACT_APP_BACKEND_URL"}}}}'
    )
    parsed = parse_response(text)
    assert parsed.action is not None
    assert parsed.action.tool == "search_code"
    assert parsed.action.args["query"] == "process.env.REACT_APP_BACKEND_URL"


def test_json_mode_thought_and_action_object():
    text = (
        '{"thought": "Read the socket file.", '
        '"action": {"tool": "read_file", "args": {"path": "client/src/Socket.js"}}}'
    )
    parsed = parse_response(text)
    assert parsed.thought == "Read the socket file."
    assert parsed.action is not None
    assert parsed.action.tool == "read_file"
    assert parsed.action.args["path"] == "client/src/Socket.js"


def test_json_mode_top_level_tool_object():
    parsed = parse_response('{"tool": "git_diff", "args": {}}')
    assert parsed.action is not None
    assert parsed.action.tool == "git_diff"
    assert parsed.action.args == {}
