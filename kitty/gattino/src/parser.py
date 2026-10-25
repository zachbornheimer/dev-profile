import re


def extract_first_code_block(text: str) -> str:
    text = text.replace('```bash', '```')
    match = re.search(r"```(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""
