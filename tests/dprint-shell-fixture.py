#!/usr/bin/env python3
"""Exercise the configured shell formatter, including the exact ZYS-11195 input."""

import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config/dprint.jsonc"
FIXTURE = ROOT / "tests/fixtures/shell-brace-substitution.sh"


def run(command, source):
    result = subprocess.run(command, input=source, capture_output=True, check=False)
    assert result.returncode == 0, (
        f"{command}: exit {result.returncode}\n{result.stderr.decode()}"
    )
    return result.stdout


def format_shell(source, filename):
    return run(
        ["dprint", "fmt", "--config", str(CONFIG), "--stdin", filename], source
    )


def without_positions(value):
    """Compare syntax, comments and literals without source byte/line coordinates."""
    if isinstance(value, dict):
        if set(value) == {"Offset", "Line", "Col"}:
            return None
        return {
            key: without_positions(item)
            for key, item in value.items()
            if key not in {"Pos", "End"}
        }
    if isinstance(value, list):
        return [without_positions(item) for item in value]
    return value


def syntax_tree(source):
    return without_positions(json.loads(run(["shfmt", "--to-json"], source)))


def main():
    original = FIXTURE.read_bytes()
    formatted = format_shell(original, "probe.sh")
    assert format_shell(formatted, "probe.sh") == formatted, "non-idempotent Bash"
    run(["bash", "-n"], formatted)
    assert syntax_tree(original) == syntax_tree(formatted), "shell syntax changed"

    # Real files exercise discovery, dotfiles and extensionless shebang dispatch.
    # Deliberately messy input must change: removing shell ownership cannot pass.
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        samples = {
            "sample.sh": b"#!/bin/sh\nprintf   '%s\\n'   ok\n",
            "sample.bash": b"#!/usr/bin/env bash\nprintf   '%s\\n'   ok\n",
            "sample.zsh": b"setopt   prompt_subst\nprint   -r -- ${(@f)words}\n",
            "sample.ksh": b"printf   '%s\\n'   ok\n",
            "sample.mksh": b"printf   '%s\\n'   ok\n",
            "sample.dash": b"printf   '%s\\n'   ok\n",
            ".envrc": b"export   EXAMPLE=value\n",
            ".bashrc": b"printf   '%s\\n'   ok\n",
            ".zshrc": b"print   -r -- ${(@f)words}\n",
            "build": b"#!/usr/bin/env bash\nprintf   '%s\\n'   ok\n",
        }
        paths = []
        for filename, source in samples.items():
            path = work / filename
            path.write_bytes(source)
            paths.append(str(path))
        command = ["dprint", "fmt", "--config", str(CONFIG), *paths]
        run(command, b"")
        first = {name: (work / name).read_bytes() for name in samples}
        for name, source in samples.items():
            assert first[name] != source, f"shell formatting disabled for {name}"
        run(command, b"")
        assert first == {name: (work / name).read_bytes() for name in samples}
        run(["dprint", "check", "--config", str(CONFIG), *paths], b"")

    # Parse failures must propagate through exec/dprint instead of returning input.
    invalid = subprocess.run(
        ["dprint", "fmt", "--config", str(CONFIG), "--stdin", "broken.sh"],
        input=b"if then\n",
        capture_output=True,
        check=False,
    )
    assert invalid.returncode != 0, "invalid shell was silently accepted"
    print("dprint shell fixture ok: exact input, idempotence, syntax, AST, dispatch, errors")


if __name__ == "__main__":
    main()
