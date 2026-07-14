"""Tests for the test-output summary parser used by run_tests."""

from app.tools.shell_tools import _parse_test_summary


def test_pytest_output():
    text = "===== 5 passed, 1 failed in 0.42s ====="
    s = _parse_test_summary(text, exit_code=1)
    assert s["passed"] == 5
    assert s["failed"] == 1
    assert s["success"] is False


def test_pytest_all_pass():
    text = "===== 47 passed in 1.2s ====="
    s = _parse_test_summary(text, exit_code=0)
    assert s["passed"] == 47
    assert s["failed"] == 0
    assert s["success"] is True


def test_jest_output():
    text = "Tests: 1 failed, 46 passed, 47 total"
    s = _parse_test_summary(text, exit_code=1)
    assert s["passed"] == 46
    assert s["failed"] == 1


def test_unknown_output():
    s = _parse_test_summary("no recognizable counts here", exit_code=0)
    assert s["success"] is True
    assert s["failed"] == 0


def test_unknown_failure_output_marks_failed_count_unknown():
    s = _parse_test_summary("FirebaseError: missing apiKey", exit_code=1)
    assert s["success"] is False
    assert s["failed"] == "?"
