def get_prompt(human_language_command: str) -> str:
    return f"""
You will be given an action in natural language to be executed on a bash shell.
Your task is to generate a single line bash command that accomplishes this action.

Requirements:
* The command must be a single line (can use pipes and semicolons if needed)
* The command should be efficient and follow best practices
* Do not use sudo unless explicitly required
* Use common bash utilities (grep, sed, awk, etc.) when appropriate

Format your response as follows:
* Only output the command in a code block
* Do not include explanations or alternatives
* Do not prefix with `$` or `#`
* Ensure the command is safe to execute

Action: {human_language_command}
"""
