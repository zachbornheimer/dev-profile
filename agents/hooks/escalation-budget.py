"""Prevent repeated escalation without research."""

import re
from datetime import datetime, timedelta


def _aware(stamp: str) -> datetime:
    """Parse an ISO timestamp; a naive one is local time."""
    parsed = datetime.fromisoformat(stamp)
    return parsed if parsed.tzinfo else parsed.astimezone()


# Session state
_session_asks = {}


def text_similarity(text1: str, text2: str) -> float:
    """Simple word-overlap similarity."""
    words1 = set(re.findall(r"\w+", text1.lower()))
    words2 = set(re.findall(r"\w+", text2.lower()))

    if not words1 or not words2:
        return 0.0

    shared = words1 & words2
    total = words1 | words2
    return len(shared) / len(total)


def handle(event: dict) -> dict:
    """
    Track PendingDecision asks and inject research prompt after repeated similar asks.
    """
    tool_name = event.get("tool_name") or event.get("name", "")

    # Only track escalation tools
    if "ask" not in tool_name.lower() and "decision" not in tool_name.lower():
        return {"decision": "allow"}

    session_id = event.get("session_id", "default")
    timestamp = event.get("timestamp") or datetime.now().astimezone().isoformat()

    # Extract question text from arguments
    args = event.get("arguments", {})
    question = args.get("question", "") or args.get("prompt", "")

    if not question:
        return {"decision": "allow"}

    # Track asks for this session
    if session_id not in _session_asks:
        _session_asks[session_id] = []

    asks = _session_asks[session_id]
    asks.append({"question": question, "timestamp": timestamp, "tool": tool_name})

    # Keep only last 10 minutes
    cutoff = datetime.now().astimezone() - timedelta(minutes=10)
    asks[:] = [a for a in asks if _aware(a["timestamp"]) > cutoff]

    # Check for repeated similar asks
    if len(asks) >= 2:
        last_two = asks[-2:]
        similarity = text_similarity(last_two[0]["question"], last_two[1]["question"])

        if similarity > 0.7:
            return {
                "decision": "modify",
                "inject_message": (
                    "⚠️  You've escalated twice with similar questions. Before asking again:\n"
                    "1. List what you've researched (web searches, docs read, tool catalogs checked)\n"
                    "2. List 3 research actions you haven't tried\n"
                    "3. Explain why user input is required vs. research\n\n"
                    f"Previous asks:\n- {last_two[0]['question'][:100]}\n- {last_two[1]['question'][:100]}"
                ),
            }

    return {"decision": "allow"}
