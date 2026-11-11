#!/usr/bin/env bash
# Verify that every enabled local Herdr plugin's manifest commands are
# executable (either via an interpreter on PATH like `sh` or an executable +x
# file under plugin_root), catching `Permission denied (os error 13)` when a
# script loses its +x bit.
set -euo pipefail

validate_plugins_json() {
	local plugins_json=$1
	/usr/bin/python3 - "$plugins_json" <<'PY'
import json
import os
import shutil
import sys

path = sys.argv[1]
if not os.path.isfile(path):
    sys.exit(0)

data = json.load(open(path, encoding="utf-8"))
plugins = data.get("plugins") if isinstance(data, dict) else data
if not isinstance(plugins, list):
    sys.exit(0)

errors = []
for plugin in plugins:
    if not isinstance(plugin, dict) or not plugin.get("enabled", False):
        continue
    if (plugin.get("source") or {}).get("kind") != "local":
        continue
    pid = plugin.get("plugin_id", "<unknown>")
    root = plugin.get("plugin_root", "")
    manifest = plugin.get("manifest_path", "")
    if not root or not os.path.isdir(root):
        errors.append(f"{pid}: missing plugin_root {root!r}")
        continue
    if not manifest or not os.path.isfile(manifest):
        errors.append(f"{pid}: missing manifest_path {manifest!r}")
        continue
    for section in ("startup", "events", "actions", "panes"):
        for item in plugin.get(section) or []:
            cmd = item.get("command") if isinstance(item, dict) else None
            if not isinstance(cmd, list) or not cmd or not isinstance(cmd[0], str) or not cmd[0]:
                errors.append(f"{pid}.{section}: empty or non-array command")
                continue
            exe = cmd[0]
            if "/" in exe:
                target = exe if os.path.isabs(exe) else os.path.join(root, exe)
                if not os.path.isfile(target):
                    errors.append(f"{pid}.{section}: command {exe!r} does not exist at {target}")
                elif not os.access(target, os.X_OK):
                    errors.append(f"{pid}.{section}: command {exe!r} is not executable (mode {oct(os.stat(target).st_mode & 0o777)})")
            else:
                if shutil.which(exe) is None:
                    errors.append(f"{pid}.{section}: interpreter/binary {exe!r} not found on PATH")

if errors:
    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    sys.exit(1)
PY
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/bad-plugin"
printf '#!/usr/bin/env bun\n' >"$tmp/bad-plugin/recover.ts"
chmod 0644 "$tmp/bad-plugin/recover.ts"
printf 'id = "bad"\n' >"$tmp/bad-plugin/herdr-plugin.toml"

cat >"$tmp/bad-plugins.json" <<EOF
[
  {
    "plugin_id": "bad",
    "enabled": true,
    "plugin_root": "$tmp/bad-plugin",
    "manifest_path": "$tmp/bad-plugin/herdr-plugin.toml",
    "source": { "kind": "local" },
    "events": [
      { "on": "pane.agent_detected", "command": ["./recover.ts", "--event"] }
    ]
  }
]
EOF

if validate_plugins_json "$tmp/bad-plugins.json" 2>/dev/null; then
	echo "FAIL: validator accepted non-executable ./recover.ts (mode 0644)" >&2
	exit 1
fi

cat >"$tmp/good-plugins.json" <<EOF
[
  {
    "plugin_id": "good",
    "enabled": true,
    "plugin_root": "$tmp/bad-plugin",
    "manifest_path": "$tmp/bad-plugin/herdr-plugin.toml",
    "source": { "kind": "local" },
    "events": [
      { "on": "pane.agent_detected", "command": ["sh", "-c", "exit 0"] }
    ]
  }
]
EOF

validate_plugins_json "$tmp/good-plugins.json"

if [ -f "$HOME/.config/herdr/plugins.json" ]; then
	validate_plugins_json "$HOME/.config/herdr/plugins.json"
fi
echo "ok"
