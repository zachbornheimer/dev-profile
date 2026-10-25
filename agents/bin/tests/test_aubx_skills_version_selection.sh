#!/usr/bin/env bash
# Proves `aubx-skills` runs the aube build a normal shell would run, not
# whichever install happens to sort first. The fallback used to hand the glob
# to the shell, so 1.26.0 won over the machine's pinned 2.7.0.
set -uo pipefail

WRAPPER="$(cd "$(dirname "$0")/.." && pwd)/aubx-skills"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP/home"
export AGENTS_HOME="$HOME/.agents"
mkdir -p "$AGENTS_HOME/available-skills" "$AGENTS_HOME/skills" "$TMP/log"

for v in 1.26.0 2.7.0; do
  d="$HOME/.local/share/mise/installs/aube/$v/.mise-bins"
  mkdir -p "$d"
  cat >"$d/aubx" <<STUB
#!/usr/bin/env bash
printf '%s\n' "$v" >>"$TMP/log/versions"
exit 1
STUB
  chmod +x "$d/aubx"
done

# Minimal PATH: no mise, no guard directory, so resolution must fall back to
# the install roots under $HOME.
env -i HOME="$HOME" AGENTS_HOME="$AGENTS_HOME" TMP="$TMP" PATH=/usr/bin:/bin \
  DRY_RUN=1 "$WRAPPER" add vercel-labs/agent-skills --skill deploy-to-vercel -g -y \
  >/dev/null 2>&1 || true

if [ ! -s "$TMP/log/versions" ]; then
  echo "FAIL - confiner never ran an installer" >&2
  exit 1
fi
ran="$(tail -n1 "$TMP/log/versions")"
if [ "$ran" != "2.7.0" ]; then
  echo "FAIL - confiner ran aube $ran, expected the newest install 2.7.0" >&2
  exit 1
fi
echo "ok   - confiner runs the newest aube install (2.7.0), not the oldest"
