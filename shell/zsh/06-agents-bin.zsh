# 06-agents-bin.zsh — keep ~/.agents/bin ahead of every later PATH writer.
#
# ~/.agents/bin holds the aubx scope guard (`aubx`, `aubx-skills`). A global
# skill install must resolve to that guard; if it resolves to mise's or
# Homebrew's real aubx, `aubx skills add -g` writes into every detected
# harness instead of ~/.agents/available-skills. 00-path.zsh puts the
# directory first, but `mise activate` (05-mise.zsh) prepends its own install
# bins afterwards, so re-assert here, after that module has run.
if [[ -d "$HOME/.agents/bin" ]]; then
	path=("$HOME/.agents/bin" ${path:#$HOME/.agents/bin})
	export PATH
fi
