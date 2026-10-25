#!/usr/bin/env bash
# Install volatile-downloads from the pinned GitHub Release into
# ~/.local/bin and ~/go/bin, then load the login LaunchAgent.
# The Personal checkout is optional (VOLATILE_DOWNLOADS_FROM_SOURCE=1).
# # rev: v0.1.3-release
# plist hash: {{ include (joinPath .chezmoi.sourceDir "Library/LaunchAgents/com.zbornheimer.volatile-downloads.plist.tmpl") | sha256sum }}
set -euo pipefail

[[ $(uname -s) == "Darwin" ]] || {
  echo "volatile-downloads: macOS only — skipping"
  exit 0
}

home="{{ .chezmoi.homeDir }}"
pin="v0.1.3"
repo="zachbornheimer/volatile-downloads"
src="${home}/Developer/Personal/volatile-downloads"
dest_local="${home}/.local/bin/volatile-downloads"
dest_gopath="${home}/go/bin/volatile-downloads"
label="com.zbornheimer.volatile-downloads"
plist="${home}/Library/LaunchAgents/${label}.plist"
domain="gui/$(id -u)"

mkdir -p "${home}/.local/bin" "${home}/go/bin" "${home}/Library/Logs"

install_bin() {
  local bin="${1}"
  install -m 755 "${bin}" "${dest_local}"
  install -m 755 "${bin}" "${dest_gopath}"
  xattr -d com.apple.quarantine "${dest_local}" "${dest_gopath}" 2>/dev/null || true
}

install_from_checkout() {
  echo "volatile-downloads: building from ${src}"
  if command -v mise >/dev/null 2>&1; then
    (cd "${src}" && mise run install)
    return 0
  fi
  local tmp
  tmp="$(mktemp -d)"
  (cd "${src}" && go build -ldflags "-s -w -X main.Version=${pin}" -o "${tmp}/volatile-downloads" ./cmd/volatile-downloads)
  install_bin "${tmp}/volatile-downloads"
  rm -rf "${tmp}"
}

asset_name() {
  case "$(uname -m)" in
  arm64) echo "volatile-downloads-darwin-arm64" ;;
  x86_64) echo "volatile-downloads-darwin-amd64" ;;
  *)
    echo "volatile-downloads: unsupported arch $(uname -m)" >&2
    return 1
    ;;
  esac
}

install_from_release() {
  local asset tmp
  asset="$(asset_name)"
  tmp="$(mktemp -d)"
  echo "volatile-downloads: gh release download ${pin} (${asset})"
  gh release download "${pin}" --repo "${repo}" --pattern "${asset}" --dir "${tmp}"
  install_bin "${tmp}/${asset}"
  rm -rf "${tmp}"
}

if [[ "${VOLATILE_DOWNLOADS_FROM_SOURCE:-}" == "1" && -d "${src}/cmd/volatile-downloads" ]]; then
  install_from_checkout
else
  install_from_release
fi

chmod +x "${dest_local}" "${dest_gopath}"
"${dest_local}" --version

if [[ ! -f "${plist}" ]]; then
  echo "volatile-downloads: ${plist} missing after apply — skip load"
  exit 0
fi

launchctl bootout "${domain}" "${plist}" 2>/dev/null || true
launchctl bootstrap "${domain}" "${plist}"
launchctl enable "${domain}/${label}" 2>/dev/null || true
launchctl kickstart -k "${domain}/${label}" 2>/dev/null || true
echo "volatile-downloads: loaded ${label}"
