from kitty.boss import Boss  # type: ignore
from src import config, model, parser, system_utils, ui


def main(args: list[str]) -> str:
    config_data = config.load_config()
    ui.print_intro()
    human_language_command = ui.print_input_line()

    if not human_language_command:
        return 0
    prompt = model.get_prompt(human_language_command)

    model_name = config_data.get('model', 'codellama')
    ollama_path = config_data.get('ollama_path', '/usr/local/bin/ollama')
    model_output = system_utils.run_command(
        f'{ollama_path} run {model_name} --nowordwrap',
        input=prompt)
    command = parser.extract_first_code_block(model_output)
    return command


def handle_result(args: list[str], answer: str, target_window_id: int, boss: Boss) -> None:
    window = boss.window_id_map.get(target_window_id)
    if window is not None:
        window.paste_text(answer)
