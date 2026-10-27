"""Shell commands an omp `eval` cell can run (ZYS-1758).

omp's eval runs Python or JS. The ManagerialBooby evidence shape is a helper,
`def sh(c, cwd=...): subprocess.run(c, shell=True, ...)`, called with string
literals; code can also call `tool.<server>_run_command({"command": ...})`, pass an
argv list (`['git', 'push', '--no-verify']`), or set a hook skip in the
environment (`env={..., 'HK': '0'}`, `os.environ['HK'] = '0'`,
`process.env.HK = '0'`). shell_candidates() returns each string literal, each
all-string list joined with spaces, and, when the code sets a skip env var,
`<VAR>=<value> <literal>` for each literal, so a shell-command checker sees the
skip in the shape it already knows.
"""

from __future__ import annotations

import ast
import contextlib
import json
import re

SKIP_VARS = ("HK", "LEFTHOOK", "HUSKY", "HK_SKIP_HOOKS", "HK_SKIP_STEPS", "SKIP")
_JS_STRING = re.compile(
    r"""'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`""", re.DOTALL
)
_JS_ENV_SKIP = re.compile(
    r"""\b(HK|LEFTHOOK|HUSKY|HK_SKIP_HOOKS|HK_SKIP_STEPS|SKIP)['"]?\s*[:=]\s*['"]([^'"]+)['"]"""
)


def _py(code: str) -> tuple[list[str], list[str]] | None:
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    strings: list[str] = []
    env: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            strings.append(
                "".join(
                    v.value if isinstance(v, ast.Constant) else "X" for v in node.values
                )
            )
        elif isinstance(node, (ast.List, ast.Tuple)):
            parts = [
                e.value
                for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            if len(parts) >= 2 and len(parts) == len(node.elts):
                strings.append(" ".join(parts))
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (
                    isinstance(k, ast.Constant)
                    and k.value in SKIP_VARS
                    and isinstance(v, ast.Constant)
                ):
                    env.append(f"{k.value}={v.value}")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value in SKIP_VARS
                    and isinstance(node.value, ast.Constant)
                ):
                    env.append(f"{target.slice.value}={node.value.value}")
        elif (
            isinstance(node, ast.keyword)
            and node.arg in SKIP_VARS
            and isinstance(node.value, ast.Constant)
        ):
            env.append(f"{node.arg}={node.value.value}")
    return strings, env


def _js(code: str) -> tuple[list[str], list[str]]:
    strings = []
    for m in _JS_STRING.finditer(code):
        single, double, tmpl = m.groups()
        text = single if single is not None else double if double is not None else tmpl
        if double is not None:
            with contextlib.suppress(ValueError):
                text = json.loads(f'"{double}"')
        strings.append(text)
    env = [f"{v}={val}" for v, val in _JS_ENV_SKIP.findall(code)]
    return strings, env


def shell_candidates(code: str, language: str = "py") -> list[str]:
    parsed = _py(code) if language in ("py", "python", "") else None
    strings, env = parsed if parsed is not None else _js(code)
    out = list(dict.fromkeys(s for s in strings if s.strip()))
    if env:
        prefix = " ".join(dict.fromkeys(env))
        out += [f"{prefix} {s}" for s in out]
    return out
