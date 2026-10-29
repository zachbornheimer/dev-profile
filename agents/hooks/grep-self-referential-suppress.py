"""Suppress self-referential Grep results where current session appears in history."""


def is_history_file(path: str) -> bool:
    """Check if path is a history/log file that might contain session records."""
    if not path:
        return False

    path_lower = path.lower()
    return any(
        pattern in path_lower
        for pattern in [
            "history.jsonl",
            "history.json",
            ".history",
            "session",
            "transcript",
            "log.json",
        ]
    )


def contains_session_id(content: str, session_id: str) -> bool:
    """Check if content contains the current session ID."""
    if not content or not session_id:
        return False

    return session_id in content


def suppress_self_referential_lines(content: str, session_id: str) -> tuple[str, int]:
    """
    Remove lines containing the current session ID from Grep output.
    Returns (filtered_content, suppressed_count).
    """
    if not content or not session_id:
        return content, 0

    lines = content.split("\n")
    filtered_lines = []
    suppressed_count = 0

    for line in lines:
        if session_id in line:
            suppressed_count += 1
        else:
            filtered_lines.append(line)

    return "\n".join(filtered_lines), suppressed_count


def handle(event: dict) -> dict:
    """
    Suppress self-referential Grep results where current session appears in history.
    """
    tool_name = event.get("tool_name") or event.get("toolName", "")

    # Only process Grep tool results
    if "grep" not in tool_name.lower():
        return {"decision": "allow"}

    session_id = event.get("session_id") or event.get("sessionId", "")
    if not session_id:
        return {"decision": "allow"}

    # Extract result content
    content = event.get("content", "") or event.get("output", "")

    if not isinstance(content, str) or not content:
        return {"decision": "allow"}

    # Check if searching in history files
    tool_input = event.get("tool_input") or event.get("toolInput", {})
    search_path = ""
    if isinstance(tool_input, dict):
        search_path = tool_input.get("path", "")

    if not is_history_file(search_path):
        # Also check if content itself suggests history files
        first_lines = content.split("\n")[:5]
        if not any(
            is_history_file(line.split(":")[0]) for line in first_lines if ":" in line
        ):
            return {"decision": "allow"}

    # Check if current session appears in results
    if not contains_session_id(content, session_id):
        return {"decision": "allow"}

    # Suppress self-referential lines
    filtered_content, suppressed_count = suppress_self_referential_lines(
        content, session_id
    )

    if suppressed_count == 0:
        return {"decision": "allow"}

    # Build message
    session_short = session_id[:8] if len(session_id) >= 8 else session_id

    if not filtered_content.strip():
        # All lines were suppressed
        message = (
            f"⚠️  All Grep results were self-referential (current session {session_short}… in history).\n"
            f"Suppressed {suppressed_count} line(s) that would have shown your own request.\n\n"
            f"To find previous work on this topic, search for keywords from the request instead of the full request text."
        )
    else:
        # Some lines remain
        message = (
            f"⚠️  Suppressed {suppressed_count} self-referential line(s) containing current session {session_short}…\n\n"
            f"{filtered_content}"
        )

    return {"decision": "modify", "inject_message": message}
