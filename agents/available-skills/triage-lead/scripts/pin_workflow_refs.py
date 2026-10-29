# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Pin floating reusable-workflow refs (@main, @v1, ...) to a SHA.

Rewrites every `uses: OWNER/REPO/.github/workflows/FILE.yml@REF` line in
`.github/workflows/*.yml|*.yaml` across a list of repos, where REF is one of
the floating refs being retired, to `@SHA # REF`. Opens one PR per repo with
changes. This clears CodeQL `actions/unpinned-tag` alerts at the source;
Renovate owns bumping the pinned SHA afterward.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REF = "main"
DEFAULT_BRANCH_NAME = "chore/pin-workflow-refs"
DEFAULT_WORKDIR = (
    Path.home() / "Developer/Software-Automation-Holdings/.worktrees/pin-refs"
)
WORKFLOW_FILE_GLOBS = ("*.yml", "*.yaml")
WORKFLOW_DIR = ".github/workflows"
FLOATING_REF_SHAPE = r"main|master|v\d+"
SHA_PREFIX_LENGTH_FOR_COMMIT_SUBJECT = 12


class CommandFailedError(RuntimeError):
    """A subprocess (git/gh) exited non-zero."""

    def __init__(self, command: list[str], stderr: str) -> None:
        super().__init__(f"command failed: {' '.join(command)}\n{stderr.strip()}")
        self.command = command
        self.stderr = stderr


def _run(command: list[str], cwd: Path | None = None) -> str:
    """Run a subprocess, returning stdout or raising CommandFailedError."""
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise CommandFailedError(command, result.stderr)
    return result.stdout


def _floating_ref_line_pattern(source: str) -> re.Pattern[str]:
    """Regex matching a `uses:` line for `source` on a floating ref."""
    return re.compile(
        r"^(?P<indent>\s*uses:\s*)"
        + re.escape(source)
        + r"(?P<path>/\.github/workflows/[^@\s]+)@(?P<ref>"
        + FLOATING_REF_SHAPE
        + r")(?:\s*#.*)?$"
    )


def rewrite(
    text: str, source: str, floating_refs: set[str], sha: str
) -> tuple[str, int]:
    """Pin every `uses: source/...@ref` line where ref is in floating_refs to sha.

    Returns the rewritten text and the number of lines changed. Lines already
    pinned to a full SHA, referencing a different source, or on a ref not in
    floating_refs are left untouched.
    """
    line_pattern = _floating_ref_line_pattern(source)
    replacement_count = 0

    def pin_matched_ref(match: re.Match[str]) -> str:
        nonlocal replacement_count
        ref = match.group("ref")
        if ref not in floating_refs:
            return match.group(0)
        replacement_count += 1
        return f"{match.group('indent')}{source}{match.group('path')}@{sha} # {ref}"

    rewritten_lines = []
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        line_ending = line[len(stripped) :]
        rewritten_lines.append(
            line_pattern.sub(pin_matched_ref, stripped) + line_ending
        )
    return "".join(rewritten_lines), replacement_count


def _workflow_files(repo_dir: Path) -> list[Path]:
    workflows_dir = repo_dir / WORKFLOW_DIR
    if not workflows_dir.is_dir():
        return []
    files: list[Path] = []
    for glob in WORKFLOW_FILE_GLOBS:
        files.extend(sorted(workflows_dir.glob(glob)))
    return files


def resolve_source_sha(source: str, ref: str) -> str:
    """Resolve `source`'s `ref` to a commit SHA via the GitHub API."""
    return _run(["gh", "api", f"repos/{source}/commits/{ref}", "-q", ".sha"]).strip()


def clone_repo(owner_repo: str, dest: Path) -> None:
    if dest.exists():
        raise CommandFailedError(
            ["gh", "repo", "clone", owner_repo, str(dest)],
            f"destination already exists: {dest}",
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(["gh", "repo", "clone", owner_repo, str(dest), "--", "--depth", "1"])


def create_branch(repo_dir: Path, branch: str) -> None:
    _run(["git", "checkout", "-b", branch], cwd=repo_dir)


def commit_changes(repo_dir: Path, message: str) -> None:
    _run(["git", "add", "-A"], cwd=repo_dir)
    _run(["git", "commit", "-S", "-m", message], cwd=repo_dir)


def push_branch(repo_dir: Path, branch: str) -> None:
    _run(["git", "push", "-u", "origin", branch], cwd=repo_dir)


def pr_already_exists(owner_repo: str, branch: str) -> bool:
    output = _run(
        ["gh", "pr", "list", "--repo", owner_repo, "--head", branch, "--json", "number"]
    )
    return output.strip() not in ("", "[]")


def create_pr(owner_repo: str, branch: str, title: str, body: str) -> str:
    return _run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            owner_repo,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ]
    ).strip()


def _pr_body(
    source: str, ref: str, sha: str, changed_files: list[Path], repo_dir: Path
) -> str:
    file_list = "\n".join(f"- {f.relative_to(repo_dir)}" for f in changed_files)
    return (
        f"Pins reusable workflow refs to `{source}@{sha}` (was `@{ref}`).\n\n"
        f"Files changed:\n{file_list}\n\n"
        "This clears the CodeQL `actions/unpinned-tag` alert for these refs. "
        "Renovate owns bumping the pinned SHA going forward."
    )


@dataclass(frozen=True)
class RepoResult:
    repo: str
    summary: str
    failed: bool = False


def process_repo(
    repo: str,
    source: str,
    ref: str,
    sha: str,
    workdir: Path,
    branch_name: str,
    apply: bool,
) -> RepoResult:
    """Clone, rewrite, and (optionally) push+PR one repo. Never raises for
    expected outcomes (no changes, existing PR); raises CommandFailedError
    only for genuine git/gh failures."""
    repo_dir = workdir / repo.split("/")[-1]
    clone_repo(repo, repo_dir)

    floating_refs = {ref}
    changed_files: list[Path] = []
    total_replacements = 0
    for workflow_file in _workflow_files(repo_dir):
        original = workflow_file.read_text()
        rewritten, count = rewrite(original, source, floating_refs, sha)
        if count == 0:
            continue
        workflow_file.write_text(rewritten)
        changed_files.append(workflow_file)
        total_replacements += count

    if total_replacements == 0:
        return RepoResult(repo, "0 refs pinned -> skipped: no matching floating refs")

    create_branch(repo_dir, branch_name)
    short_sha = sha[:SHA_PREFIX_LENGTH_FOR_COMMIT_SUBJECT]
    commit_changes(
        repo_dir,
        f"ci: pin {source} reusable workflow refs to {short_sha} (was @{ref})",
    )

    file_count = len(changed_files)
    outcome_prefix = f"{total_replacements} refs pinned in {file_count} files ->"

    if not apply:
        return RepoResult(repo, f"{outcome_prefix} dry-run")

    if pr_already_exists(repo, branch_name):
        return RepoResult(
            repo, f"{outcome_prefix} skipped: PR already open for {branch_name}"
        )

    push_branch(repo_dir, branch_name)
    pr_url = create_pr(
        repo,
        branch_name,
        title=f"ci: pin {source} reusable workflow refs to {short_sha}",
        body=_pr_body(source, ref, sha, changed_files, repo_dir),
    )
    return RepoResult(repo, f"{outcome_prefix} {pr_url}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pin floating reusable-workflow refs to a SHA across repos."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="OWNER/REPO whose reusable-workflow refs should be pinned",
    )
    parser.add_argument(
        "--ref",
        default=DEFAULT_REF,
        help=f"floating ref to pin (default: {DEFAULT_REF})",
    )
    parser.add_argument(
        "repos",
        nargs="+",
        metavar="REPO",
        help="OWNER/REPO to scan and rewrite",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="push branches and open PRs (default: dry run, no push)",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=DEFAULT_WORKDIR,
        help=f"scratch clone directory (default: {DEFAULT_WORKDIR})",
    )
    parser.add_argument(
        "--branch-name",
        default=DEFAULT_BRANCH_NAME,
        help=f"branch name to create in each repo (default: {DEFAULT_BRANCH_NAME})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    sha = resolve_source_sha(args.source, args.ref)

    results: list[RepoResult] = []
    failed_repos: list[str] = []
    for repo in args.repos:
        try:
            result = process_repo(
                repo=repo,
                source=args.source,
                ref=args.ref,
                sha=sha,
                workdir=args.workdir,
                branch_name=args.branch_name,
                apply=args.apply,
            )
        except CommandFailedError as error:
            results.append(RepoResult(repo, f"error: {error}", failed=True))
            failed_repos.append(repo)
        else:
            results.append(result)

    for result in results:
        print(f"{result.repo}: {result.summary}")

    if failed_repos:
        print(f"failed: {', '.join(failed_repos)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
