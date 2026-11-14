#!/usr/bin/env bash
# dev-profile-changed-files hands a per-file step only the files this push
# introduces. A file is introduced when its content at the pushed tip differs
# from every base the push inherited: the ref's remote tip (advanced to the
# default branch's merge base when the branch moved onto a newer one, and the
# branch's published tip when the remote is unborn), the merge base with
# origin's default branch, and the published parents of the pushed tip — the
# upstream line a fork branch merged in, which the push did not write. Without
# push refs (pre-commit, `hk run check`, a direct run) a candidate is judged
# when this checkout introduces it against the mainline; a checkout that
# introduces nothing must not run the step's tool at all.
set -euo pipefail

src="$(cd "$(dirname "$0")/.." && pwd)"
work="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "${work}"' EXIT
fail() {
	echo "FAIL: $*" >&2
	exit 1
}

export GIT_CONFIG_GLOBAL="${work}/gitconfig" GIT_CONFIG_NOSYSTEM=1
git config --file "${GIT_CONFIG_GLOBAL}" user.name fixture
git config --file "${GIT_CONFIG_GLOBAL}" user.email fixture@example.invalid
git config --file "${GIT_CONFIG_GLOBAL}" commit.gpgsign false

# The recording command stands in for a step's tool: it prints the files it
# was handed, so the fixture can assert exactly which candidates reached it.
cat >"${work}/record.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@"
EOF
chmod +x "${work}/record.sh"

repo="${work}/repo"
git init -q -b main "${repo}"
cd "${repo}"
printf 'main\n' >main.md
git add main.md
git commit -q -m main
git update-ref refs/remotes/origin/main HEAD

git switch -q -c upstream
printf 'upstream\n' >upstream.md
git add upstream.md
git commit -q -m upstream-file
git update-ref refs/remotes/upstream/main HEAD

git switch -q main
git switch -q -c topic
printf 'topic\n' >topic.txt
git add topic.txt
git commit -q -m topic-file
topic_tip="$(git rev-parse HEAD)"
git update-ref refs/remotes/origin/topic HEAD

git merge -q --no-edit upstream
merge="$(git rev-parse HEAD)"

gate() {
	"${src}/bin/dev-profile-changed-files" "${work}/record.sh" -- "$@" \
		>"${work}/passed" 2>"${work}/log"
}
push() { # <local_sha> <remote_sha> <candidate>...
	printf 'refs/heads/topic %s refs/heads/topic %s\n' "$1" "$2" >"${work}/refs"
	DEV_PROFILE_PUSH_REFS="${work}/refs" gate "${@:3}"
}
gate_added() {
	"${src}/bin/dev-profile-changed-files" --added "${work}/record.sh" -- "$@" \
		>"${work}/passed" 2>"${work}/log"
}
push_added() { # <local_sha> <remote_sha> <candidate>...
	printf 'refs/heads/topic %s refs/heads/topic %s\n' "$1" "$2" >"${work}/refs"
	DEV_PROFILE_PUSH_REFS="${work}/refs" gate_added "${@:3}"
}
step_added() { # <local_sha> <remote_sha> <candidate>...
	printf 'refs/heads/topic %s refs/heads/topic %s\n' "$1" "$2" >"${work}/refs"
	DEV_PROFILE_PUSH_REFS="${work}/refs" \
		"${src}/bin/dev-profile-changed-files" --added hk util check-added-large-files -- "${@:3}"
}

# A push of the merged branch hands the step its remote tip, the default
# branch's merge base, and the published parents of the merge: nothing is
# introduced, so the tool must not run at all.
push "${merge}" "${topic_tip}" main.md topic.txt upstream.md
if [ -s "${work}/passed" ]; then
	fail "a fully inherited push must run no tool: $(cat "${work}/passed")"
fi
grep -Eq '0 of 3 candidate file\(s\) introduced by this push.*skipped' "${work}/log" ||
	fail "the skip must be logged: $(cat "${work}/log")"

# An unborn remote falls back to the branch's own published tip; the push still
# introduces nothing.
push "${merge}" 0000000000000000000000000000000000000000 main.md topic.txt upstream.md
if [ -s "${work}/passed" ]; then
	fail "an unborn remote with a published tip must run no tool: $(cat "${work}/passed")"
fi

# A branch stacked on a published branch of another name, first pushed under
# its own name, is measured from the nearest published commit: two commits
# above origin/topic introduce only the files they add, not topic.txt. The tip's
# parent is unpublished, so only the boundary of the unpublished history finds
# the base.
stack_tip="${topic_tip}"
for name in stacked-one stacked-two; do
	GIT_INDEX_FILE="${work}/stack-index" git read-tree "${stack_tip}"
	blob="$(printf '%s\n' "${name}" | git hash-object -w --stdin)"
	GIT_INDEX_FILE="${work}/stack-index" git update-index --add --cacheinfo "100644,${blob},${name}.md"
	tree="$(GIT_INDEX_FILE="${work}/stack-index" git write-tree)"
	stack_tip="$(git commit-tree -p "${stack_tip}" -m "${name}" "${tree}")"
done
printf 'refs/heads/stacked %s refs/heads/stacked %s\n' \
	"${stack_tip}" 0000000000000000000000000000000000000000 >"${work}/refs"
DEV_PROFILE_PUSH_REFS="${work}/refs" gate topic.txt stacked-one.md stacked-two.md
printf 'stacked-one.md\nstacked-two.md\n' >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "a branch stacked on a published branch must judge only its own files: $(cat "${work}/passed")"
fi

# A commit authored on top of the merge is the push's own work. The merge is
# not published anywhere yet, so the upstream file it carried in is judged as
# introduced too; files only the older history touched stay inherited.
printf 'authored\n' >authored.md
git add authored.md
git commit -q -m authored
push "$(git rev-parse HEAD)" "${topic_tip}" main.md topic.txt upstream.md authored.md
printf 'authored.md\nupstream.md\n' | sort >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "only the authored and unpublished-merge files are introduced: $(cat "${work}/passed")"
fi
grep -Eq '2 of 4 candidate file\(s\) introduced by this push.*running' "${work}/log" ||
	fail "the run must be logged: $(cat "${work}/log")"

# A push whose tip is already the remote tip introduces nothing.
push "$(git rev-parse HEAD)" "$(git rev-parse HEAD)" main.md topic.txt upstream.md authored.md
if [ -s "${work}/passed" ]; then
	fail "a tip already on the remote must run no tool: $(cat "${work}/passed")"
fi

# The shared measurement a pre-push hands every step through
# DEV_PROFILE_PUSH_INTRODUCED must agree with what the per-step fallback
# judges for the same push.
printf 'refs/heads/topic %s refs/heads/topic %s\n' \
	"$(git rev-parse HEAD)" "$(git rev-parse HEAD^)" >"${work}/refs"
"${src}/bin/dev-profile-push-base" <"${work}/refs" >"${work}/advanced"
introduced="${work}/introduced"
"${src}/bin/dev-profile-push-introduced" "${work}/advanced" >"${introduced}"
printf 'authored.md\n' >"${work}/want"
sort "${introduced}" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "the shared measurement must list the authored file: $(cat "${introduced}")"
fi

# A union handed through DEV_PROFILE_PUSH_INTRODUCED filters the step's
# candidates without touching git.
DEV_PROFILE_PUSH_INTRODUCED="${introduced}" gate main.md authored.md
printf 'authored.md\n' >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "a shared union must filter the candidates: $(cat "${work}/passed}")"
fi
grep -Eq '1 of 2 candidate file\(s\) introduced by this push.*running' "${work}/log" ||
	fail "the shared-union run must be logged: $(cat "${work}/log}")"

# A union that cannot bound the push runs the tool on every candidate.
printf '*\n' >"${introduced}"
DEV_PROFILE_PUSH_INTRODUCED="${introduced}" gate main.md authored.md
printf 'authored.md\nmain.md\n' | sort >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "an unmeasurable push must run every candidate: $(cat "${work}/passed}")"
fi

# An empty shared union introduces nothing, so the tool must not run.
: >"${introduced}"
DEV_PROFILE_PUSH_INTRODUCED="${introduced}" gate main.md authored.md
if [ -s "${work}/passed" ]; then
	fail "an empty shared union must skip the tool: $(cat "${work}/passed}")"
fi
grep -Eq '0 of 2 candidate file\(s\) introduced by this push.*skipped' "${work}/log" ||
	fail "the shared-union skip must be logged: $(cat "${work}/log}")"

# An unreadable shared union falls back to measuring the push per step.
DEV_PROFILE_PUSH_INTRODUCED="${work}/missing-union" \
	DEV_PROFILE_PUSH_REFS="${work}/refs" gate main.md authored.md
printf 'authored.md\n' >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "a missing shared union must fall back to the refs: $(cat "${work}/passed}")"
fi

# --added hands a step only the files the push adds: present at the pushed
# tip, absent at every base. A file the bases already track is never the
# push's to add, so a modified tracked file must not reach the step, and the
# shared changed-union must not be consulted for it.
printf 'main edited\n' >main.md
git commit -q -a -m edited-main
push_added "$(git rev-parse HEAD)" "${topic_tip}" main.md topic.txt upstream.md authored.md
printf 'authored.md\nupstream.md\n' | sort >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "--added must keep the modified tracked file out: $(cat "${work}/passed}")"
fi
grep -Eq '2 of 4 candidate file\(s\) added by this push.*running' "${work}/log" ||
	fail "the --added run must be logged: $(cat "${work}/log}")"

# The shared measurement must agree: --added lists only the files the push
# adds, never the files it only modifies.
printf 'refs/heads/topic %s refs/heads/topic %s\n' \
	"$(git rev-parse HEAD)" "${topic_tip}" >"${work}/refs"
"${src}/bin/dev-profile-push-base" <"${work}/refs" >"${work}/advanced"
"${src}/bin/dev-profile-push-introduced" --added "${work}/advanced" >"${introduced}"
printf 'authored.md\nupstream.md\n' | sort >"${work}/want"
sort "${introduced}" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "the --added measurement must drop the modified file: $(cat "${introduced}")"
	fail "the --added measurement must drop the modified file: $(cat "${introduced}")"
fi

# DEV_PROFILE_PUSH_INTRODUCED measures changed files, not added ones, so
# --added must measure from the refs itself even when it is set.
printf 'main.md\n' >"${introduced}"
DEV_PROFILE_PUSH_INTRODUCED="${introduced}" DEV_PROFILE_PUSH_REFS="${work}/refs" \
	gate_added main.md authored.md
printf 'authored.md\n' >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "--added must not trust the shared changed-union: $(cat "${work}/passed}")"
	fail "--added must not trust the shared changed-union: $(cat "${work}/passed}")"
fi
grep -Eq '1 of 2 candidate file\(s\) added by this push.*running' "${work}/log" ||
	fail "the --added own-measurement run must be logged: $(cat "${work}/log}")"

# A push that only modifies tracked files adds nothing, so the step skips.
printf 'refs/heads/topic %s refs/heads/topic %s\n' \
	"$(git rev-parse HEAD)" "$(git rev-parse HEAD^)" >"${work}/refs"
DEV_PROFILE_PUSH_REFS="${work}/refs" gate_added main.md authored.md
if [ -s "${work}/passed" ]; then
	fail "a push that adds nothing must run no tool: $(cat "${work}/passed}")"
fi
grep -Eq '0 of 2 candidate file\(s\) added by this push.*skipped' "${work}/log" ||
	fail "the --added skip must be logged: $(cat "${work}/log}")"

# A push that cannot be measured judges every candidate, in --added mode too.
printf 'refs/heads/topic %s refs/heads/topic %s\n' \
	0000000000000000000000000000000000000000 0000000000000000000000000000000000000000 >"${work}/refs"
DEV_PROFILE_PUSH_REFS="${work}/refs" gate_added main.md
printf 'main.md\n' >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "an unmeasurable push must run every candidate: $(cat "${work}/passed}")"
	fail "an unmeasurable push must run every candidate: $(cat "${work}/passed}")"
fi
grep -q 'no parsable push refs' "${work}/log" ||
	fail "the unmeasured --added run must be logged: $(cat "${work}/log}")"

# Without push refs --added falls back to the mainline: a candidate origin's
# default branch already tracks is not added, whatever the step would say
# about its size; the rest reach the step as they would anywhere.
unset DEV_PROFILE_PUSH_REFS DEV_PROFILE_PUSH_INTRODUCED
gate_added main.md topic.txt upstream.md authored.md
printf 'authored.md\ntopic.txt\nupstream.md\n' | sort >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "--added without push refs must keep mainline-tracked files out: $(cat "${work}/passed}")"
fi
grep -Eq '3 of 4 candidate file\(s\) added.*running' "${work}/log" ||
	fail "the mainline --added run must be logged: $(cat "${work}/log}")"

gate_added main.md
if [ -s "${work}/passed" ]; then
	fail "a mainline-tracked candidate must not reach the tool: $(cat "${work}/passed}")"
fi
grep -Eq '0 of 1 candidate file\(s\) added.*skipped' "${work}/log" ||
	fail "the mainline --added skip must be logged: $(cat "${work}/log}")"
# Without push refs (pre-commit, `hk run check`, a direct run) a candidate is
# judged when this checkout introduces it against the mainline: its content
# at the working tree differs from the merge base with origin's default
# branch, or the mainline does not track it. Here the branch has moved past
# origin/main, so every candidate is this checkout's own work.
unset DEV_PROFILE_PUSH_REFS DEV_PROFILE_PUSH_INTRODUCED
gate main.md topic.txt upstream.md authored.md
printf 'authored.md\nmain.md\ntopic.txt\nupstream.md\n' | sort >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "a checkout past the mainline must introduce every candidate: $(cat "${work}/passed}")"
fi
grep -Eq '4 of 4 candidate file\(s\) introduced by this checkout: running' "${work}/log" ||
	fail "the no-refs introduced run must be logged: $(cat "${work}/log}")"

# A clean checkout at the mainline introduces nothing, so the tool must not
# run at all — the case a repo-wide `hk run check` lands in on a synced tree.
git update-ref refs/remotes/origin/main HEAD
gate main.md topic.txt upstream.md authored.md
if [ -s "${work}/passed" ]; then
	fail "a clean checkout at the mainline must run no tool: $(cat "${work}/passed}")"
fi
grep -Eq '0 of 4 candidate file\(s\) introduced by this checkout.*skipped' "${work}/log" ||
	fail "the clean-checkout skip must be logged: $(cat "${work}/log}")"

# Working-tree and untracked edits are this checkout's own work too: a dirty
# tracked file reaches the step alone, an untracked one beside it.
printf 'main dirtied\n' >main.md
printf 'fresh\n' >fresh.txt
gate main.md topic.txt fresh.txt
printf 'fresh.txt\nmain.md\n' | sort >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "dirty and untracked files must reach the step alone: $(cat "${work}/passed}")"
fi
grep -Eq '2 of 3 candidate file\(s\) introduced by this checkout: running' "${work}/log" ||
	fail "the dirty-tree run must be logged: $(cat "${work}/log}")"
git checkout -q -- main.md
rm fresh.txt

# DEV_PROFILE_CHANGED_FILES_ALL=1 restores the judgment of every candidate.
DEV_PROFILE_CHANGED_FILES_ALL=1 gate main.md topic.txt
printf 'main.md\ntopic.txt\n' | sort >"${work}/want"
sort "${work}/passed" >"${work}/got"
if ! diff -q "${work}/want" "${work}/got" >/dev/null; then
	fail "the escape hatch must run every candidate: $(cat "${work}/passed}")"
fi
grep -q 'DEV_PROFILE_CHANGED_FILES_ALL=1' "${work}/log" ||
	fail "the escape-hatch run must be logged: $(cat "${work}/log}")"
unset DEV_PROFILE_CHANGED_FILES_ALL

# A step with no candidates exits 0 without running its tool.
DEV_PROFILE_PUSH_REFS="${work}/refs" gate
if [ -s "${work}/passed" ] || [ -s "${work}/log" ]; then
	fail "an empty candidate list must run no tool and log nothing"
fi

# The separator is required: without it nothing can run.
if "${src}/bin/dev-profile-changed-files" "${work}/record.sh" main.md \
	>"${work}/passed" 2>"${work}/log"; then
	fail "a command without the -- separator must be refused"
fi
grep -q 'usage:' "${work}/log" || fail "the refusal must explain the usage: $(cat "${work}/log")"

# End to end through the real util: a tracked 665 KB file the push only
# modifies passes the step; the same push adding a fresh large file fails it.
big=big.bin
head -c 665000 /dev/zero | tr '\0' 'b' >"${big}"
git add "${big}"
git commit -q -m big-tracked
git update-ref refs/remotes/origin/main HEAD
printf 'b' >>"${big}"
git commit -q -a -m big-modified
step_added "$(git rev-parse HEAD)" "$(git rev-parse HEAD^)" "${big}" ||
	fail "a push that only modifies a tracked large file must pass the step"

head -c 665000 /dev/zero | tr '\0' 'c' >fresh.bin
git add fresh.bin
git commit -q -m fresh-large
if step_added "$(git rev-parse HEAD)" "$(git rev-parse HEAD^)" fresh.bin; then
	fail "a push that adds a fresh large file must fail the step"
fi

# --added still requires the separator.
if "${src}/bin/dev-profile-changed-files" --added "${work}/record.sh" main.md \
	>"${work}/passed" 2>"${work}/log"; then
	fail "an --added command without the -- separator must be refused"
fi
grep -q 'usage:' "${work}/log" ||
	fail "the --added refusal must explain the usage: $(cat "${work}/log}")"

echo "ok changed-files fixture"
