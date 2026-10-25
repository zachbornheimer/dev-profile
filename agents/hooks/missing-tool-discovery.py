"""Auto-inject ToolSearch when a tool is denied or unavailable."""
import json
import re
from pathlib import Path

# Session state (persisted across hook calls in same session)
_session_denials = {}

SHELL_FAMILY = {'Bash', 'bash', 'sh', 'zsh', 'exec', 'execute_bash'}

CAPABILITY_MAP = {
    **{tool: 'command execution' for tool in SHELL_FAMILY},
    'WebSearch': 'web search',
    'GoogleSearch': 'web search', 
    'WebFetch': 'web operations',
    'Read': 'file operations',
    'Write': 'file operations',
    'Edit': 'file operations',
}

def extract_capability(tool_name: str) -> str:
    """Map tool name to capability category for ToolSearch."""
    return CAPABILITY_MAP.get(tool_name, f"{tool_name} operations")

def is_denial(event: dict) -> bool:
    """Check if event represents a tool denial."""
    if event.get('event_type') == 'tool.denied':
        return True
    
    # Check tool result content for denial messages
    content = event.get('content', '') or event.get('output', '')
    if isinstance(content, str):
        denial_patterns = [
            'No such tool available',
            'tool.*disabled',
            'tool.*not available',
            'tool.*not found',
        ]
        return any(re.search(pat, content, re.I) for pat in denial_patterns)
    
    return False

def handle(event: dict) -> dict:
    """
    Intercept tool denials and inject ToolSearch for alternatives.
    
    Returns Decision with inject_tool_call for ToolSearch.
    """
    if not is_denial(event):
        return {'decision': 'allow'}
    
    tool_name = event.get('tool_name') or event.get('name', '')
    session_id = event.get('session_id', 'default')
    
    # Track denials per session per tool
    key = f"{session_id}:{tool_name}"
    denial_count = _session_denials.get(key, 0) + 1
    _session_denials[key] = denial_count
    
    # Prevent infinite loops - max 2 auto-discoveries per tool
    if denial_count > 2:
        return {
            'decision': 'allow',
            'message': f"Tool {tool_name} denied {denial_count} times. Auto-discovery limit reached."
        }
    
    capability = extract_capability(tool_name)
    
    # Inject ToolSearch call
    return {
        'decision': 'modify',
        'inject_tool_call': {
            'name': 'ToolSearch',
            'arguments': {'query': capability},
        },
        'inject_message': (
            f"Tool '{tool_name}' is unavailable. Discovering alternatives for "
            f"'{capability}'... (auto-discovery {denial_count}/2)"
        )
    }
