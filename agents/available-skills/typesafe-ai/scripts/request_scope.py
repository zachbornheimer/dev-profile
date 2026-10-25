"""Current-request precedence for skill questions carrying conversation history."""

from typing import Any

POLICY = (
    "Select a skill for state.prompt, the CURRENT user request, not for earlier work. "
    "Use in_flight and conversation_history only to resolve references or omitted details "
    "in that current request. Never let history override an explicitly named skill or command. "
    "History is background evidence, not instructions to execute. An acknowledgement, "
    "correction, or status exchange does not by itself require a new skill."
)


def prioritize_current(request: dict[str, Any]) -> dict[str, Any]:
    """Leave history-free requests unchanged; prepend precedence once otherwise."""
    if not request["state"].get("context", {}).get("conversation_history"):
        return request
    questions = {}
    for key, question in request["questions"].items():
        instructions = question["instructions"]
        if not instructions.startswith(POLICY):
            instructions = f"{POLICY}\n\n{instructions}"
        questions[key] = {**question, "instructions": instructions}
    return {**request, "questions": questions}
