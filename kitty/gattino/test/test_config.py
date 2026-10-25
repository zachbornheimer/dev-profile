import json
import os
import unittest
from unittest.mock import mock_open, patch

from src import config


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.test_config = {
            "model": "codellama"
        }
        self.config_path = os.path.expanduser(
            '~/.config/kitty/gattino/gattino.config.json')

    def test_load_config_success(self):
        mock_json = json.dumps(self.test_config)
        with patch('builtins.open', mock_open(read_data=mock_json)):
            result = config.load_config()
            self.assertEqual(result, self.test_config)

    def test_load_config_file_not_found(self):
        with patch('builtins.open', side_effect=FileNotFoundError):
            result = config.load_config()
            self.assertEqual(result, {})

    def test_load_config_invalid_json(self):
        with patch('builtins.open', mock_open(read_data='invalid json')):
            result = config.load_config()
            self.assertEqual(result, {})


if __name__ == '__main__':
    unittest.main()
