#!/bin/zsh
# Set every appearance-tracking surface to match current macOS appearance:
# kitty theme and window borders.
# Runs at login and on appearance changes via LaunchAgent. Re-run manually after
# switching appearance, then restart kitty or ctrl+shift+F5 to reload config.
set -euo pipefail

THEMES="${HOME}/.config/kitty/themes"

if defaults read -g AppleInterfaceStyle 2>/dev/null | grep -q Dark; then
	THEME="dark"
else
	THEME="light"
fi

ln -sf "${THEMES}/${THEME}.conf" "${THEMES}/active.conf"
printf '%s' "${THEME}" >"${HOME}/.config/borders/current-theme.tmp"
mv "${HOME}/.config/borders/current-theme.tmp" "${HOME}/.config/borders/current-theme"

if [[ -x /opt/homebrew/bin/borders ]]; then
	killall borders 2>/dev/null || true
	/opt/homebrew/bin/borders &
fi

# Apply the matching Kitty auto-theme to all running Kitty instances without restarting.
if [[ -x /opt/homebrew/bin/kitten && -f "${HOME}/.config/kitty/${THEME}-theme.auto.conf" ]]; then
	setopt null_glob 2>/dev/null || true
	for sock in /tmp/kitty-*; do
		[[ -S "${sock}" ]] || continue
		/opt/homebrew/bin/kitten @ --to "unix:${sock}" set-colors --all --configured \
			"${HOME}/.config/kitty/${THEME}-theme.auto.conf" >/dev/null 2>&1 || true
	done
fi

# Notify open interactive Zsh shells so TRAPWINCH updates STARSHIP_CONFIG and redraws.
pkill -WINCH -u "${UID}" -x zsh 2>/dev/null || true
printf '%s theme=%s\n' \
	"$(date '+%F %T')" "${THEME}" >&2
