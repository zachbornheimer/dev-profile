import unittest

from src import parser


class TestModel(unittest.TestCase):
    def test_extract_first_code_block(self):
        text = "Some text\n```\ncode block\n```\nmore text"
        result = parser.extract_first_code_block(text)
        self.assertEqual(result, "code block")

    def test_extract_first_code_block_with_no_blocks(self):
        text = "Some text without code blocks"
        result = parser.extract_first_code_block(text)
        self.assertEqual(result, "")

    def test_extract_first_code_block_with_bash(self):
        text = "Some text\n```bash\ncode block\n```\nmore text"
        result = parser.extract_first_code_block(text)
        self.assertEqual(result, "code block")


if __name__ == '__main__':
    unittest.main()
