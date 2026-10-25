import unittest

from src import model


class TestModel(unittest.TestCase):
    def test_prompt_includes_command(self):
        command = "list all python files"
        result = model.get_prompt(command)
        self.assertIn(command, result)

    def test_prompt_includes_requirements(self):
        result = model.get_prompt("list files")
        self.assertIn("Requirements", result)

    def test_prompt_includes_format(self):
        result = model.get_prompt("list files")
        self.assertIn("Format", result)

    def test_prompt_longer_than_action(self):
        action = "list files"
        result = model.get_prompt(action)
        self.assertGreater(len(result), len(action))


if __name__ == '__main__':
    unittest.main()
