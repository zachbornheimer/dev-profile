import subprocess
import sys
import threading

from src import ui


def write_file(path: str, content: str) -> None:
    """Write content to a file at the specified path."""
    with open(path, 'w') as file:
        file.write(content + '\n')


def run_command(command: str, input: str | None = None) -> str:
    process = subprocess.Popen(
        command.split(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Start spinner in background thread
    spinner_thread = threading.Thread(target=ui.show_spinner, args=(process,))
    spinner_thread.start()

    # Send input and get output
    stdout, stderr = process.communicate(input=input)

    # Wait for spinner to finish
    spinner_thread.join()

    if stderr:
        print(stderr, end='', file=sys.stderr)

    return stdout
