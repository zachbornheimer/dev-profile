import json
from os import path


def load_config() -> dict:
    config_path = path.expanduser("~/.config/kitty/gattino/gattino.config.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        print(f"Config file not found at {config_path}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing config file: {e}")
        return {}
