#!/bin/zsh
# Set every appearance-tracking surface to match current macOS appearance:
# kitty theme, window borders, and the Hermes agent skin.
# Runs at login and on appearance changes via LaunchAgent. Re-run manually after
# switching appearance, then restart kitty or ctrl+shift+F5 to reload config.
set -euo pipefail

THEMES="${HOME}/.config/kitty/themes"

if defaults read -g AppleInterfaceStyle 2>/dev/null | grep -q Dark; then
  THEME="dark"
  # Hermes skins are authored for ONE canvas polarity (ink and art are picked
  # against a named background), so the agent follows the same switch the
  # terminal does rather than guessing from a color table.
  HERMES_SKIN="rose-pine"
else
  THEME="light"
  HERMES_SKIN="rose-pine-dawn"
fi

ln -sf "${THEMES}/${THEME}.conf" "${THEMES}/active.conf"
printf '%s' "${THEME}" >"${HOME}/.config/borders/current-theme.tmp"
mv "${HOME}/.config/borders/current-theme.tmp" "${HOME}/.config/borders/current-theme"

killall borders 2>/dev/null || true
/opt/homebrew/bin/borders &

# Fail-soft: a missing or broken agent CLI must not cost the terminal its theme.
# LaunchAgents run with a minimal PATH; the installed wrapper hardcodes its own
# interpreter, so the absolute path is all it needs.
hermes_bin="$(command -v hermes 2>/dev/null || true)"
[[ -n "${hermes_bin}" ]] || hermes_bin="${HOME}/.hermes/hermes-agent/.hermes/bin/hermes"
applied="skipped"
if [[ -x "${hermes_bin}" ]]; then
  applied="ok"
  "${hermes_bin}" skin use "${HERMES_SKIN}" >/dev/null 2>&1 || applied="failed"
fi
printf '%s theme=%s hermes_skin=%s skin_apply=%s\n' \
  "$(date '+%F %T')" "${THEME}" "${HERMES_SKIN}" "${applied}" >&2
