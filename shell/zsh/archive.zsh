uz2() {
	local dest="$1"
	local zip="$2"

	if [[ -z "$dest" || -z "$zip" ]]; then
		__ -t failed "Usage: uz2 <destination-folder> <zip-file>"
		return 1
	fi

	if [[ ! -f "$zip" ]]; then
		__ -t failed "Zip not found: $zip"
		return 1
	fi

	mkdir -p "$dest" || return 1

	local tmp
	tmp="$(mktemp -d)" || return 1

	unzip -q "$zip" -d "$tmp" || {
		rm -rf "$tmp"
		return 1
	}

	local entries=()
	entries=("${(@f)$(find "$tmp" -mindepth 1 -maxdepth 1)}")

	if ((${#entries} == 1)) && [[ -d "${entries[1]}" ]]; then
		cp -R "${entries[1]}/." "$dest/"
	else
		cp -R "$tmp/." "$dest/"
	fi

	rm -rf "$tmp"
}
