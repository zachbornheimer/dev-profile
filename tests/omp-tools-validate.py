"""Check installed tool imports and actual OMP extension registration without model calls."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SUFFIXES = (".ts", ".js", ".mts", ".mjs", ".cjs")
# These paths are selected from the installed plugin registry at runtime.
IMPORT_TOOL = """
const mod = await import(process.argv[1]);
const factory = typeof mod.default === 'function' ? mod.default : mod.default?.default;
if (typeof factory !== 'function') throw new Error('Tool default export must be a function');
"""


def entries(directory):
    if not directory.is_dir():
        return []
    result = []
    for child in sorted(directory.iterdir()):
        if child.name.startswith(".") or child.name == "node_modules":
            continue
        if child.is_file() and child.suffix in SUFFIXES:
            result.append(child)
        elif child.is_dir():
            for suffix in SUFFIXES:
                entry = child / ("index" + suffix)
                if entry.is_file():
                    result.append(entry)
                    break
    return result


def run(command, timeout, cwd, input_text=None):
    try:
        result = subprocess.run(
            command,
            input=input_text,
            text=True,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, str(error)
    if result.returncode:
        return None, f"exit {result.returncode}: {result.stderr or result.stdout}"
    return result, None


def check_tools(files, cwd):
    failures = []
    if not files:
        return failures
    bun = shutil.which("bun")
    if not bun:
        return ["bun is required to validate installed custom tools"]
    for entry in files:
        _, error = run([bun, "--no-install", "-e", IMPORT_TOOL, str(entry)], 20, cwd)
        if error:
            failures.append(f"tool {entry}: {error}")
    return failures


def check_extensions(files, cwd):
    if not files:
        return []
    omp = shutil.which("omp")
    if not omp:
        return ["omp is required to validate installed extension registration"]
    command = [
        omp,
        "--mode",
        "rpc",
        "--no-ui",
        "--no-session",
        "--no-extensions",
        "--no-tools",
        "--no-skills",
        "--no-rules",
        "--no-context-files",
        "--no-title",
        "--no-lsp",
    ]
    for entry in files:
        command.extend(["--extension", str(entry)])
    # EOF exits RPC mode. get_state proves initialization completed; no prompt is
    # sent, so the health check never requests a model turn or invokes any tool.
    result, error = run(command, 90, cwd, '{"id":"omp-health","type":"get_state"}\n')
    if error:
        return [f"extensions: {error}"]
    failures = []
    ready = False
    for line in result.stdout.splitlines():
        try:
            frame = json.loads(line)
        except ValueError:
            continue
        if not isinstance(frame, dict):
            continue
        if frame.get("type") == "extension_error":
            failures.append(
                f"extension {frame.get('extensionPath')}: {frame.get('error')}"
            )
        if frame.get("type") == "response" and frame.get("id") == "omp-health":
            ready = frame.get("success") is True
    # The host reports import/registration failures on stderr, even when its
    # process exits zero. Never turn those warnings into a passing health check.
    if result.stderr.strip():
        failures.append(f"extension startup diagnostics: {result.stderr.strip()}")
    if not ready:
        failures.append("OMP did not acknowledge get_state after extension startup")
    return failures


def main():
    agent = Path(os.environ.get("OMP_AGENT_DIR", Path.home() / ".omp/agent")).resolve()
    tools = entries(agent / "tools")
    extensions = entries(agent / "extensions")
    if not tools and not extensions:
        print(f"SKIP: no installed OMP entry modules under {agent}")
        return 0
    with tempfile.TemporaryDirectory(prefix="omp-health-") as cwd:
        failures = check_tools(tools, cwd) + check_extensions(extensions, cwd)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        f"ok: {len(tools)} tool imports and {len(extensions)} host extension registrations"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
