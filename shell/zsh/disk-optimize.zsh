# Unique APFS physical size: merged F_LOG2PHYS_EXT spans (same as ~/test.zsh _bm_scan).
# Walk without following symlinks; skip other devices (same as --one-fs).
optimize::unique-bytes() {
	uv run --no-project --quiet python - "$1" <<'PY'
import fcntl, os, stat, struct, sys

F_LOG2PHYS_EXT = 65
FMT = "<Iqq"

def walk_files(root):
    root_dev = os.stat(root).st_dev
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        keep = []
        for name in dirnames:
            p = os.path.join(dirpath, name)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode) and st.st_dev == root_dev:
                keep.append(name)
        dirnames[:] = keep
        for name in filenames:
            p = os.path.join(dirpath, name)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and st.st_dev == root_dev:
                yield p, st

def file_spans(path, size):
    spans = []
    fd = os.open(path, os.O_RDONLY)
    try:
        off = 0
        while off < size:
            remaining = size - off
            out = fcntl.fcntl(
                fd, F_LOG2PHYS_EXT, struct.pack(FMT, 0, remaining, off)
            )
            _, contig, devoffset = struct.unpack(FMT, out[:20])
            if contig <= 0:
                raise OSError("non-positive contig")
            if contig > remaining:
                contig = remaining
            spans.append((devoffset, devoffset + contig))
            off += contig
    finally:
        os.close(fd)
    return spans

def merge_len(spans):
    if not spans:
        return 0
    spans.sort()
    total = 0
    start, end = spans[0]
    for s, e in spans[1:]:
        if s <= end:
            if e > end:
                end = e
        else:
            total += end - start
            start, end = s, e
    return total + (end - start)

def measure(root):
    spans = []
    fallback = {}
    for path, st in walk_files(root):
        if st.st_size == 0:
            continue
        try:
            spans.extend(file_spans(path, st.st_size))
        except OSError:
            fallback[(st.st_dev, st.st_ino)] = st.st_blocks * 512
    return merge_len(spans) + sum(fallback.values())

sys.stdout.write(str(measure(sys.argv[1])))
PY
}

# optimize [folder]
#   fclones group+dedupe on one tree (default .). Do not follow symlink contents.
#   Before/After/Delta are unique physical extents, not hash-group totals.
optimize() {
	emulate -L zsh
	setopt no_monitor no_notify
	local red=$'\e[31m' green=$'\e[32m' gray=$'\e[90m' reset=$'\e[0m'

	if (($# > 1)); then
		__ -t failed "optimize accepts at most one folder."
		return 1
	fi
	local dir=${1:-.}
	local phys
	phys=$(builtin cd -P -- "$dir" && pwd -P) || return 1

	if ! command -v fclones >/dev/null 2>&1; then
		__ -t failed "fclones is not on PATH."
		return 1
	fi

	local tmp
	tmp=$(mktemp -d)
	_optimize_cleanup() { rm -rf -- "$tmp"; }
	trap '_optimize_cleanup' EXIT INT

	__ -o stderr "Scanning $phys"
	optimize::unique-bytes "$phys" >"$tmp/unique_before" &
	local unique_pid=$!
	if ! fclones --progress=true group --format json --one-fs --hidden --no-ignore "$phys" \
		>"$tmp/groups.json"; then
		kill $unique_pid 2>/dev/null
		wait $unique_pid 2>/dev/null
		__ -t failed "fclones group failed."
		return 1
	fi
	wait $unique_pid || {
		__ -t failed "unique size scan failed."
		return 1
	}
	local unique_before
	unique_before=$(<"$tmp/unique_before")

	local report
	report=$(uv run --no-project --quiet python -c '
import json, sys
raw = open(sys.argv[1], "r", encoding="utf-8").read().strip()
data = None
groups = []
if raw:
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            groups = data
        elif isinstance(data, dict):
            groups = data.get("groups") or data.get("duplicates") or []
    except json.JSONDecodeError:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            groups.append(json.loads(line))
stats = {}
if isinstance(data, dict):
    header = data.get("header") or {}
    stats = header.get("stats") or data.get("stats") or {}
group_count = int(stats.get("group_count") or 0)
total_file_count = int(stats.get("total_file_count") or 0)
if not stats:
    total_file_count = 0
    group_count = 0
    for g in groups:
        files = g.get("files") or g.get("paths") or []
        nfiles = len(files)
        if nfiles == 0:
            continue
        total_file_count += nfiles
        group_count += 1
print("%d\t%d" % (group_count, total_file_count))
' "$tmp/groups.json") || return 1

	local group_count total_file_count
	group_count=${report%%$'\t'*}
	total_file_count=${report#*$'\t'}

	local unique_after=$unique_before
	if ((group_count > 0)); then
		__ -o stderr "Deduping $group_count groups"
		if ! fclones --progress=true dedupe <"$tmp/groups.json"; then
			__ -t failed "fclones dedupe failed."
			return 1
		fi
		unique_after=$(optimize::unique-bytes "$phys") || return 1
	fi

	local delta=$((unique_after - unique_before))
	local color sign
	if ((unique_after < unique_before)); then
		color=$green
		sign='-'
	elif ((unique_after > unique_before)); then
		color=$red
		sign='+'
	else
		color=$gray
		sign=' '
	fi
	local abs=$delta
	((abs < 0)) && abs=$((-abs))
	__ -t success "Optimized $phys ($group_count groups, $total_file_count files)"
	printf 'Before: %s\n' "$(go::human-size "$unique_before")"
	printf 'After:  %s\n' "$(go::human-size "$unique_after")"
	printf 'Delta:  %s%s%s%s\n' "$color" "$sign" "$(go::human-size "$abs")" "$reset"
	return 0
}
