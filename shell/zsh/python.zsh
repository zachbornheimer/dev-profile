# python.zsh — uv-owned Python toolchain and the fence around system Python.

# Runtimes — mise via shims on PATH (see 00-path.zsh). Avoids `mise activate` + per-prompt
# hook-env. Shims resolve node/go/ruby on first use. `mise use -g …` still works.
# uv still owns Python; mise is not configured for Python.
# Escape hatch for full env activation: eval "$(mise activate zsh)"

# Python — uv owns the user toolchain.
#
# Contract:
#   • /usr/bin/python3 stays for macOS/Xcode scripts that hardcode that path.
#   • Everything else (you, installers, agents, `#!/usr/bin/env python3`) must
#     hit uv-managed CPython via ~/.local/bin — never system or Homebrew.
#   • Projects: `uv venv` / `uv run`. Global tools: `uv tool install`.
#   • Versions: `uv python install` (shims land in ~/.local/bin).
#
# Policy also lives in:
#   ~/.zshenv              UV_PYTHON_PREFERENCE / PIP_REQUIRE_VIRTUALENV
#   ~/.config/uv/uv.toml   python-preference = only-managed
#   ~/.config/pip/pip.conf require-virtualenv = true
#
# User bins + mise shims already first on PATH (see 00-path.zsh).

# True if this interpreter is user-managed (uv / venv / tool env), not OS/Brew.
python::is-user-managed() {
	local bin="$1"
	local real="${bin:A}"
	[[ "$real" == "$HOME/.local/share/uv/python/"* ]] && return 0
	[[ "$real" == "$HOME/.local/share/uv/tools/"* ]] && return 0
	[[ "$real" == "$HOME/.local/pipx/"* ]] && return 0
	[[ -n "${VIRTUAL_ENV:-}" && "$real" == "${VIRTUAL_ENV:A}/"* ]] && return 0
	[[ "$real" == */.venv/* ]] && return 0
	return 1
}

python::deny() {
	local name="$1" bin="$2"
	__ -t failed "python-fence: blocked \`${name}\` → ${bin}"
	__ "python-fence: system/Homebrew Python is reserved for the OS." >&2
	__ "python-fence: use \`uv run …\`, \`uv tool run …\`, or a project .venv." >&2
	return 126
}

# Interactive/shell-function gate: bare python/pip never reach /usr/bin or Cellar.
python::run() {
	local name="$1"
	shift
	local bin
	bin="$(whence -p "$name" 2>/dev/null)" || {
		__ -t failed "python-fence: \`${name}\` not on PATH (expected uv shim in ~/.local/bin)"
		return 127
	}
	if ! python::is-user-managed "$bin"; then
		python::deny "$name" "$bin"
		return $?
	fi
	"$bin" "$@"
}

python::run-pip() {
	local name="$1"
	shift
	# Prefer invoking pip as a module of the fenced interpreter.
	if whence -w python3 >/dev/null 2>&1; then
		python::run python3 -m pip "$@"
		return $?
	fi
	local bin
	bin="$(whence -p "$name" 2>/dev/null)" || {
		__ -t failed "python-fence: \`${name}\` not on PATH"
		return 127
	}
	# If the pip binary itself lives under brew/system, refuse.
	local real="${bin:A}"
	case "$real" in
	/opt/homebrew/* | /usr/local/Cellar/* | /usr/bin/*)
		python::deny "$name" "$bin"
		return $?
		;;
	esac
	"$bin" "$@"
}

python() { python::run python "$@"; }
python3() { python::run python3 "$@"; }
pip() { python::run-pip pip "$@"; }
pip3() { python::run-pip pip3 "$@"; }

# Versioned shims (python3.12, etc.) — same gate when typed interactively.
for _pyver in python3.12 python3.13 python3.14; do
	# Only define if a real shim exists; avoids shadowing nothing useful.
	if [[ -x "$HOME/.local/bin/${_pyver}" ]]; then
		eval "${_pyver}() { python::run ${_pyver} \"\$@\"; }"
	fi
done
unset _pyver

uvr() {
	emulate -L zsh
	local -a pkgs=() files=() snippets=() withs=() missing=()
	local a probe
	local -i i

	while (($#)); do
		case "$1" in
		--with | -w)
			[[ -n ${2:-} ]] || {
				__ -t failed "uvr: --with needs a package"
				return 2
			}
			pkgs+=("$2")
			shift 2
			;;
		*) break ;;
		esac
	done

	for ((i = 1; i <= $#; i++)); do
		a="${@[i]}"
		[[ $a == *.py && -f $a ]] && files+=("$a")
		[[ $a == -c && -n ${@[i+1]:-} ]] && snippets+=("${@[i+1]}")
	done

	if ((${#pkgs} || ${#files} || ${#snippets})); then
		probe='
import ast, importlib.util, os, sys
from pathlib import Path

def collect(src: str, names: list[str]) -> None:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module.split(".")[0])

names = [n for n in os.environ.get("UVR_PKGS", "").split("\n") if n]
for path in os.environ.get("UVR_FILES", "").split("\n"):
    if path:
        try:
            collect(Path(path).read_text(encoding="utf-8"), names)
        except OSError:
            pass
for src in os.environ.get("UVR_SNIPPETS", "").split("\0"):
    if src:
        collect(src, names)

stdlib = sys.stdlib_module_names | set(sys.builtin_module_names)
seen: set[str] = set()
for raw in names:
    spec_name = raw.split("[", 1)[0].replace("-", "_")
    if not spec_name or spec_name in seen or spec_name in stdlib:
        continue
    seen.add(spec_name)
    if importlib.util.find_spec(spec_name) is None:
        print(raw.split("[", 1)[0])
'
		missing=("${(@f)$(
			UVR_PKGS="${(F)pkgs}" UVR_FILES="${(F)files}" UVR_SNIPPETS="${(j:\0:)snippets}" \
				UV_NO_PROGRESS=1 command uv -q run python -c "$probe" 2>/dev/null
		)}")
		for a in "${missing[@]}"; do
			[[ -n $a ]] && withs+=(--with "$a")
		done
	fi

	UV_NO_PROGRESS=1 command uv -q run "${withs[@]}" "$@"
}
