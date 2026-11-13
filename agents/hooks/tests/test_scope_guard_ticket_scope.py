"""A resumed ticket keeps acceptance criteria visible to the scope judge."""

from lib.scope_decide import Ask, _task_of


def test_long_ticket_preserves_acceptance_between_operator_and_comments():
    acceptance = "Re-run ZYS-9084 and verify only native webmaster tools are called."
    request = (
        "Operator rules\n"
        + "Use the existing branch and pull request.\n" * 150
        + "<user-input>\nThe ticket:\nZYS-9110: Native Relay tooling\n"
        + "## Deliverable\nNative tools only.\n## Acceptance criteria\n- "
        + acceptance
        + "\nComments, oldest first:\n"
        + "Routine historical comment.\n" * 100
        + "This turn's instruction:\nResume and finish the remaining work.\n</user-input>"
    )
    task = _task_of((Ask(request, "2026-11-13T00:00:00Z"),))
    assert acceptance in task
    assert "Resume and finish" in task
