from app.agent.types import AgentStatus
from app.db.models import RunStatus
from app.queue.processor import _agent_exception_message, _final_run_status


def test_final_run_status_marks_pr_failure_as_failed():
    assert _final_run_status(AgentStatus.SOLVED, "push failed") == RunStatus.FAILED


def test_final_run_status_keeps_solved_when_pr_succeeds():
    assert _final_run_status(AgentStatus.SOLVED, None) == RunStatus.SOLVED


def test_agent_exception_message_explains_openai_429():
    message = _agent_exception_message(
        RuntimeError("Client error '429 Too Many Requests' for url 'https://api.openai.com'")
    )

    assert "provider returned 429" in message
    assert "billing" in message


def test_agent_exception_message_unwraps_retry_error_last_attempt():
    class LastAttempt:
        def exception(self):
            return RuntimeError(
                "Client error '429 Too Many Requests' for url 'https://api.openai.com'"
            )

    class RetryLikeError(Exception):
        last_attempt = LastAttempt()

        def __str__(self):
            return "RetryError[hidden]"

    message = _agent_exception_message(RetryLikeError())

    assert "provider returned 429" in message
