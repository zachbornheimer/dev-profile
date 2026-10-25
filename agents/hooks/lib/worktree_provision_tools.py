"""Facade over the external tools worktree-provision.py uses after wt
creates the worktree: chezmoi (locate the dotfiles source repo) and
aube/composer (dependency install).
"""

from __future__ import annotations

import os
import shutil
import subprocess

AUBE_FALLBACK_PATHS = (
    "{home}/.local/share/mise/shims/aube",
    "{home}/.local/bin/aube",
)


def chezmoi_source_path() -> str | None:
    if shutil.which("chezmoi") is None:
        return None
    result = subprocess.run(["chezmoi", "source-path"], capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def resolve_aube() -> str | None:
    found = shutil.which("aube")
    if found:
        return found
    home = os.environ.get("HOME", "")
    for template in AUBE_FALLBACK_PATHS:
        candidate = template.format(home=home)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def run_install(args: list[str], cwd: str | None, timeout_secs: float) -> bool:
    try:
        result = subprocess.run(
            args, cwd=cwd, capture_output=True, timeout=timeout_secs, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def composer_on_path() -> bool:
    return shutil.which("composer") is not None


def provision_dependencies(
    repo_root: str, dest: str, timeout_secs: float, log
) -> None:  # HookLog, kept untyped to avoid a hook_common import cycle
    import os

    env_src = os.path.join(repo_root, ".env")
    env_dst = os.path.join(dest, ".env")
    if os.path.isfile(env_src) and not os.path.exists(env_dst):
        try:
            with open(env_src, "rb") as source, open(env_dst, "wb") as target:
                target.write(source.read())
            log.record("provision", f".env copied into {dest}")
        except OSError:
            log.record("provision-warn", f".env copy failed for {dest}")

    if os.path.isfile(os.path.join(dest, "package.json")):
        aube_bin = resolve_aube()
        if aube_bin:
            if run_install([aube_bin, "install", "--dir", dest], None, timeout_secs):
                log.record("provision", f"aube install ok in {dest}")
            else:
                log.record("provision-warn", f"aube install failed in {dest}")
        else:
            log.record("provision-warn", f"aube not found on PATH; skipped install for {dest}")

    if os.path.isfile(os.path.join(dest, "composer.json")) and composer_on_path():
        if run_install(["composer", "install", "--no-interaction", "--quiet"], dest, timeout_secs):
            log.record("provision", f"composer install ok in {dest}")
        else:
            log.record("provision-warn", f"composer install failed in {dest}")
