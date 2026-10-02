from app.verification import compare_verification


def test_equal_failure_counts_do_not_hide_different_test_identity() -> None:
    result = compare_verification(
        {"success": False, "failed_tests": ["tests/test_a.py::test_a"]},
        {"success": False, "failed_tests": ["tests/test_b.py::test_b"]},
    )
    assert result["regression"] is True
    assert result["new_failures"] == ["tests/test_b.py::test_b"]
