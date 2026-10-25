"""Detect binary/encrypted content in Grep results and warn the agent."""
import re


def calculate_entropy(text: str) -> float:
    """Calculate Shannon entropy of text. High entropy (~7-8) suggests encryption/compression."""
    if not text:
        return 0.0
    
    import math
    from collections import Counter
    
    counts = Counter(text)
    length = len(text)
    
    entropy = 0.0
    for count in counts.values():
        probability = count / length
        entropy -= probability * math.log2(probability)
    
    return entropy

def is_likely_binary(content: str) -> tuple[bool, str]:
    """
    Detect if Grep output contains binary/encrypted content.
    Returns (is_binary, reason).
    """
    if not content:
        return False, ""
    
    # Check for high ratio of non-printable/non-ASCII characters
    printable_count = sum(1 for c in content if c.isprintable() or c in '\n\r\t')
    non_printable_ratio = 1 - (printable_count / len(content))
    
    if non_printable_ratio > 0.3:
        return True, f"High non-printable character ratio: {non_printable_ratio:.1%}"
    
    # Check for base64-like patterns (long strings of alphanumeric+/+=)
    base64_pattern = r'[A-Za-z0-9+/]{40,}={0,2}'
    base64_matches = re.findall(base64_pattern, content)
    
    if base64_matches:
        # Calculate entropy of the base64-like content
        sample = base64_matches[0][:200]
        entropy = calculate_entropy(sample)
        
        # High entropy + base64 pattern = likely encrypted/compressed
        if entropy > 5.5:
            return True, f"Base64-encoded high-entropy data (entropy: {entropy:.1f}/8)"
    
    # Check for very high entropy overall (encrypted/compressed data)
    if len(content) > 100:
        sample = content[:500]
        entropy = calculate_entropy(sample)
        
        if entropy > 6.5:
            return True, f"Very high entropy content (entropy: {entropy:.1f}/8) - likely encrypted/compressed"
    
    return False, ""

def handle(event: dict) -> dict:
    """
    Detect binary/encrypted content in Grep results and inject warning.
    """
    tool_name = event.get('tool_name') or event.get('name', '')
    
    # Only process Grep tool results
    if 'grep' not in tool_name.lower():
        return {'decision': 'allow'}
    
    # Extract result content
    content = event.get('content', '') or event.get('output', '')
    
    if not isinstance(content, str) or not content:
        return {'decision': 'allow'}
    
    is_binary, reason = is_likely_binary(content)
    
    if is_binary:
        return {
            'decision': 'modify',
            'inject_message': (
                f"⚠️  Grep returned binary/encrypted content that is likely not useful.\n"
                f"Reason: {reason}\n\n"
                f"This match is probably in an encrypted session file, compiled binary, "
                f"or compressed archive. Consider:\n"
                f"1. Excluding these file types with --glob patterns\n"
                f"2. Searching in source directories only\n"
                f"3. Using file extension filters (.py, .ts, .md, etc.)\n"
            )
        }
    
    return {'decision': 'allow'}
