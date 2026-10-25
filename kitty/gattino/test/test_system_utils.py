import os
import sys
import threading
import unittest

from src import system_utils


class TestSystemUtils(unittest.TestCase):
    def test_write_file(self):
        test_content = "test content"
        test_path = "test_file.txt"
        system_utils.write_file(test_path, test_content)

        with open(test_path, 'r') as file:
            content = file.read().strip()
        self.assertEqual(content, test_content)

        # Cleanup
        import os
        os.remove(test_path)

    def test_run_command(self):
        # Test basic command
        result = system_utils.run_command("echo hello")
        self.assertEqual(result.strip(), "hello")

        # Test command with input
        result = system_utils.run_command("cat", input="test input")
        self.assertEqual(result.strip(), "test input")

        # Test command with error
        with open(os.devnull, 'w') as devnull:
            old_stderr = sys.stderr
            sys.stderr = devnull
            result = system_utils.run_command("ls nonexistentfile")
            sys.stderr = old_stderr
        self.assertEqual(result.strip(), "")

    def test_run_command_shows_spinner(self):
        # Mock the spinner thread to verify it was started
        original_Thread = threading.Thread
        thread_started = False

        def mock_Thread(*args, **kwargs):
            nonlocal thread_started
            if kwargs.get('target') == system_utils.ui.show_spinner:
                thread_started = True
            return original_Thread(*args, **kwargs)

        threading.Thread = mock_Thread

        try:
            # Run a command that will take a moment
            system_utils.run_command("sleep 0.1")
            self.assertTrue(thread_started, "Spinner thread was not started")
        finally:
            # Restore original Thread class
            threading.Thread = original_Thread


if __name__ == '__main__':
    unittest.main()
