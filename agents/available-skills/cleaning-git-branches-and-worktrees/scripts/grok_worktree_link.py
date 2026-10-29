#!/usr/bin/env python3
"""Turn Grok's standalone clones (~/.grok/worktrees/<slug>/subagent-*) into linked
worktrees of their source repo, in place, so `wt step relocate` can move them.

Per clone (metadata only, no checkout, no file copies):
  1. fetch the clone's HEAD, stash, and commits the source lacks into the source repo
     (stash and unique branches land under refs/grok/<id>/...);
  2. create branch grok/<id>/<branch> at the clone's HEAD in the source repo;
  3. `git worktree add --no-checkout` a throwaway worktree, then graft its `.git` file
     onto the clone and `git worktree repair` it, so git owns the admin dir format;
  4. carry the clone's index over (dirty state preserved byte for byte);
  5. move the clone's old `.git` dir to ~/.grok/worktree-gits/<slug>/<name> (never deleted).

Skips and reports: stale/missing source, nested linked worktrees, submodules, in-progress
rebase/merge/cherry-pick/bisect, split index, recently active clones, already linked.

Default is a dry run. Pass --apply to change anything.
"""

import argparse
import glob
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

# Apple git: the mise git shim adds seconds per call, which dominates over 780 clones.
GIT = "/usr/bin/git"
ROOT = os.path.expanduser("~/.grok/worktrees")
BACKUP = os.path.expanduser("~/.grok/worktree-gits")
BUSY_FILES = (
    "rebase-merge",
    "rebase-apply",
    "MERGE_HEAD",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
    "BISECT_LOG",
)


def git(path, *a, check=False):
    r = subprocess.run(
        [GIT, "-C", path, *a], capture_output=True, text=True, check=False
    )
    if check and r.returncode:
        raise RuntimeError(f"git -C {path} {' '.join(a)}: {r.stderr.strip()}")
    return r.returncode, r.stdout.strip()


def short_id(name):
    u = name.removeprefix("subagent-")
    return u[:8] + "-" + u[-4:]


def git_dir(dir_, *a, check=False):
    """git against an explicit --git-dir, which -C cannot express."""
    r = subprocess.run(
        [GIT, "--git-dir", dir_, *a], capture_output=True, text=True, check=False
    )
    if check and r.returncode:
        raise RuntimeError(f"git --git-dir {dir_} {' '.join(a)}: {r.stderr.strip()}")
    return r.returncode, r.stdout.strip()


def submodules(clone):
    """[(name, absolute workdir)] for each submodule the clone has checked out."""
    if not os.path.exists(clone + "/.gitmodules"):
        return []
    rc, out = git(
        clone, "config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$"
    )
    if rc:
        return []
    found = []
    for line in out.splitlines():
        key, _, path = line.partition(" ")
        name = key[len("submodule.") : -len(".path")]
        workdir = os.path.normpath(os.path.join(clone, path))
        if os.path.isfile(os.path.join(workdir, ".git")):
            found.append((name, workdir))
    return found


def plan(d, min_idle):
    name = os.path.basename(d)
    gd = d + "/.git"
    if not os.path.isdir(gd):
        return None, "already linked or not a clone"
    try:
        src = pathlib.Path(gd + "/grok-worktree-source").read_text().strip()
    except OSError:
        return None, "no grok-worktree-source"
    if not os.path.exists(src + "/.git"):
        return None, f"source missing: {src}"
    if os.path.isdir(gd + "/worktrees") and os.listdir(gd + "/worktrees"):
        return None, "has nested linked worktrees"
    # A submodule's git dir lives in .git/modules. Adoption carries modules/ into the
    # worktree's admin dir and repoints each checkout, so nothing is stranded.
    subs = submodules(d)
    mods = gd + "/modules"
    if os.path.isdir(mods) and os.listdir(mods) and not subs:
        return None, "submodule git dirs present but no initialised checkout"
    if any(os.path.exists(f"{gd}/{f}") for f in BUSY_FILES):
        return None, "operation in progress"
    if glob.glob(gd + "/sharedindex.*"):
        return None, "split index"
    try:
        idle = time.time() - os.path.getmtime(gd + "/index")
    except OSError:
        return None, "no index"
    if idle < min_idle:
        return None, f"active {int(idle)}s ago"
    rc, head = git(d, "rev-parse", "HEAD")
    if rc:
        return None, "no HEAD"
    _, branch = git(d, "branch", "--show-current")
    return {
        "dir": d,
        "name": name,
        "slug": os.path.basename(os.path.dirname(d)),
        "src": src,
        "head": head,
        "branch": branch or "detached",
        "id": short_id(name),
        "subs": subs,
    }, None


def apply(p):
    d, src, id_, name = p["dir"], p["src"], p["id"], p["name"]
    new_branch = f"grok/{id_}/{p['branch']}"
    # 1. objects + stash + unique branches into the source repo
    specs = ["HEAD"]
    if git(d, "rev-parse", "--verify", "--quiet", "refs/stash")[0] == 0:
        specs.append(f"+refs/stash:refs/grok/{id_}/stash")
    _, refs = git(
        d, "for-each-ref", "--format=%(objectname) %(refname:short)", "refs/heads"
    )
    unique = []
    if refs:
        pairs = [l.split(" ", 1) for l in refs.splitlines()]
        chk = subprocess.run(
            [GIT, "-C", src, "cat-file", "--batch-check"],
            input="".join(f"{s}^{{commit}}\n" for s, _ in pairs),
            capture_output=True,
            text=True,
            check=False,
        ).stdout.splitlines()
        unique = [r for (s, r), out in zip(pairs, chk) if out.endswith("missing")]
    specs.extend(f"+refs/heads/{ref}:refs/grok/{id_}/heads/{ref}" for ref in unique)
    git(src, "fetch", "--no-tags", "--quiet", d, *specs, check=True)
    # 2+3. branch + throwaway worktree, graft its .git onto the clone
    if git(src, "show-ref", "--verify", "--quiet", f"refs/heads/{new_branch}")[0] == 0:
        raise RuntimeError(f"branch {new_branch} already exists in {src}")
    tmp = f"/tmp/grok-link-{id_}"
    if os.path.exists(tmp):
        # A crashed run can leave this behind; the same clone always maps to the same path.
        shutil.rmtree(tmp, ignore_errors=True)
        git(src, "worktree", "prune")
    git(
        src,
        "worktree",
        "add",
        "--no-checkout",
        "-b",
        new_branch,
        tmp,
        p["head"],
        check=True,
    )
    bk = f"{BACKUP}/{p['slug']}"
    os.makedirs(bk, exist_ok=True)
    old = f"{bk}/{name}"
    # A submodule's core.worktree is relative to the clone's .git, so it stops resolving
    # the moment .git is renamed, and an absolute value breaks the next time the checkout
    # moves. Unset it: git then derives the worktree from the checkout's own .git pointer,
    # which stays correct wherever the worktree ends up.
    pointers, admin_modules, worktrees = {}, None, {}
    for name_, _ in p["subs"]:
        module = f"{d}/.git/modules/{name_}"
        worktrees[name_] = git_dir(module, "config", "--get", "core.worktree")[1]
        git_dir(module, "config", "--unset", "core.worktree")
    os.rename(d + "/.git", old)
    try:
        shutil.copy(tmp + "/.git", d + "/.git")
        git(src, "worktree", "repair", d, check=True)
        # 4. carry the index (dirty/staged state) into the new admin dir
        _, admin = git(d, "rev-parse", "--absolute-git-dir", check=True)
        shutil.copy(f"{old}/index", f"{admin}/index")
        # 5. carry submodule git dirs too, and repoint each checkout at its new home.
        # Absolute pointers survive a later `wt relocate`, which moves the checkout but
        # not the admin dir.
        if p["subs"]:
            admin_modules = os.path.join(admin, "modules")
            if os.path.isdir(f"{old}/modules"):
                shutil.move(f"{old}/modules", admin_modules)
            for name_, workdir in p["subs"]:
                pointer = os.path.join(workdir, ".git")
                pointers[pointer] = pathlib.Path(pointer).read_text(errors="replace")
                target = os.path.join(admin_modules, name_)
                if not os.path.isdir(target):
                    raise RuntimeError(
                        f"submodule {name_}: git dir missing at {target}"
                    )
                pathlib.Path(pointer).write_text(f"gitdir: {target}\n")
                # `git submodule` decides a submodule is initialised from these entries.
                # They lived in the clone's config, which is now the backup, so carry them
                # across or the checkout reports as uninitialised.
                for key in ("url", "active"):
                    rc_, val = git_dir(
                        old, "config", "--get", f"submodule.{name_}.{key}"
                    )
                    if rc_ == 0 and val:
                        git_dir(admin, "config", f"submodule.{name_}.{key}", val)
    except Exception:
        # Rollback must run for any failure raised after .git was renamed.
        # restore the original clone .git first: the relative core.worktree only resolves
        # once modules/ is back under it.
        if os.path.exists(d + "/.git"):
            os.remove(d + "/.git")
        os.rename(old, d + "/.git")
        if admin_modules and os.path.isdir(admin_modules):
            shutil.move(admin_modules, f"{d}/.git/modules")
        for pointer, text in pointers.items():
            pathlib.Path(pointer).write_text(text)
        for name_, val in worktrees.items():
            module = f"{d}/.git/modules/{name_}"
            if os.path.isdir(module):
                git_dir(module, "config", "core.worktree", val)
        git(src, "worktree", "remove", "--force", tmp)
        git(src, "worktree", "prune")
        git(src, "branch", "-D", new_branch)
        raise
    shutil.rmtree(tmp, ignore_errors=True)
    return new_branch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", help="substring of clone path; repeatable via comma")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--min-idle",
        type=int,
        default=1800,
        help="skip clones whose index changed within N seconds",
    )
    a = ap.parse_args()
    only = a.only.split(",") if a.only else None
    done = skipped = failed = 0
    for d in sorted(glob.glob(ROOT + "/*/subagent-*")):
        if only and not any(o in d for o in only):
            continue
        p, why = plan(d, a.min_idle)
        if not p:
            skipped += 1
            print(json.dumps({"dir": d, "skip": why}), flush=True)
            continue
        if a.limit and done >= a.limit:
            break
        try:
            br = apply(p) if a.apply else f"grok/{p['id']}/{p['branch']}"
            done += 1
            print(
                json.dumps(
                    {"dir": d, "src": p["src"], "branch": br, "applied": a.apply}
                ),
                flush=True,
            )
        except (OSError, RuntimeError, ValueError, KeyError) as e:
            # One clone failing must not abort the sweep; it is reported and counted.
            failed += 1
            print(json.dumps({"dir": d, "error": str(e)}), flush=True)
    print(
        json.dumps(
            {
                "summary": {
                    "converted" if a.apply else "would_convert": done,
                    "skipped": skipped,
                    "failed": failed,
                }
            }
        ),
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
