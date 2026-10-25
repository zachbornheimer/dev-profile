#!/usr/bin/env bash
# Install / refresh Evident Output: MCP binary + portable cli-output skill.
# Re-runs when this script's content hash changes (chezmoi run_onchange).
# # rev: v0.2.11-pin-maintenance
set -euo pipefail

home="{{ .chezmoi.homeDir }}"
dest="${home}/.local/bin/evident-output-mcp"
pin="v0.2.11"
mkdir -p "${home}/.local/bin"

install_skill() {
  local skill_src="${1}"
  if [[ ! -f "${skill_src}" ]]; then
    return 0
  fi
  local d
  for d in \
    "${home}/.claude/skills/cli-output" \
    "${home}/.codex/skills/cli-output"
  do
    mkdir -p "${d}"
    if [[ -d "${d}/references" ]]; then
      rm -rf "${d}/references"
    fi
    cp "${skill_src}" "${d}/SKILL.md"
    # Append machine-local MCP notes (portable skill has no host paths).
    {
      echo ""
      echo "## Local MCP (this machine)"
      echo ""
      echo "Binary: \`~/.local/bin/evident-output-mcp\` (chezmoi"
      echo "\`run_onchange_after_install-evident-output-mcp\`, pin **${pin}**)."
      echo ""
      echo '```bash'
      echo "evident-output-mcp --version"
      echo "evident-output-mcp config --client grok"
      echo "grok mcp doctor evident-output"
      echo '```'
    } >>"${d}/SKILL.md"
    echo "cli-output skill: installed → ${d}/SKILL.md"
  done
}

# Prefer upstream portable skill from local evo checkout (always current on this Mac).
# Fall back to module-pinned install after go install (no skill in module).
skill_candidates=(
  "${home}/Developer/Personal/evident-output/skills/cli-output/SKILL.md"
  "${home}/.dotfiles/home/dot_claude/skills/cli-output/SKILL.md"
  "${home}/Developer/Personal/dotfiles/home/dot_claude/skills/cli-output/SKILL.md"
)

install_best_skill() {
  local candidate
  for candidate in "${skill_candidates[@]}"; do
    if [[ -f "${candidate}" ]]; then
      install_skill "${candidate}"
      return 0
    fi
  done
}

# Prefer local checkout (development machine). Stamp PublishedRelease into Version.
src="${home}/Developer/Personal/evident-output"
if [[ -d "${src}/cmd/evident-output-mcp" ]]; then
  echo "evident-output-mcp: building from ${src}"
  local_pin="${pin}"
  if [[ -f "${src}/release.go" ]]; then
    local_pin="$(sed -n 's/^const PublishedRelease = "\(v[^"]*\)"/\1/p' "${src}/release.go" | head -1)"
    [[ -n "${local_pin}" ]] || local_pin="${pin}"
  fi
  (cd "${src}" && go build -ldflags "-X main.Version=${local_pin}" -o "${dest}" ./cmd/evident-output-mcp)
  chmod +x "${dest}"
  "${dest}" --version || true
  install_best_skill
  exit 0
fi

# Fallback: module install — pin release (never @latest).
echo "evident-output-mcp: go install @${pin} (no local checkout)"
GOBIN="${home}/.local/bin" go install "github.com/zachbornheimer/evident-output/cmd/evident-output-mcp@${pin}"
chmod +x "${dest}"
"${dest}" --version || true
install_best_skill
