# Screenshot inbox shims (uv project: ~/Developer/Personal/screenshot-inbox)
#   sc-path  — copy newest inbox image path
#   sc-ocr   — copy OCR text of newest inbox image
#   sc-pin   — pin newest (or path) to archive/pinned
# Full CLI: uv run --project ~/Developer/Personal/screenshot-inbox screenshot-inbox <cmd>

# mdb — Markdown Browser: render a .md file and open it in the default browser.
# Replaces the cx → markdownlivepreview paste dance for local docs.
# Implementation: ~/.local/bin/md-preview (also Raycast "Preview Markdown").
mdb() {
	emulate -L zsh

	local target_file="${1:-}"
	local preview="${HOME}/.local/bin/md-preview"

	if [[ -z $target_file ]]; then
		__ -t failed "usage: mdb <file.md>"
		return 2
	fi

	if [[ ! -f $target_file ]]; then
		__ -t failed "mdb: file not found: $target_file"
		return 1
	fi

	if [[ ! -x $preview ]]; then
		__ -t failed "mdb: md-preview not found at $preview"
		return 1
	fi

	"$preview" "$target_file"
}
