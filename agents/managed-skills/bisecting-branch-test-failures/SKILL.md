---
name: bisecting-branch-test-failures
description: Decide whether a failing test in a branch worktree is caused by the branch or by the environment, by swapping in the base branch's version of each touched file.
---

# Bisecting branch test failures against the base

Use when a test fails in a feature-branch worktree and you must say whether the branch caused it or the environment did. Do not guess "flaky" or "pre-existing" — this produces a per-file verdict in a few minutes.

## 1. Confirm the branch touches the suspect code

```sh
cd <main checkout>
git diff --name-only <base>...<branch> | rg -i '<module>|\.test\.ts'
```

If the branch touches nothing in the failing path, the failure is environmental and this procedure ends. Evidence: the empty diff.

## 2. Baseline the whole set at once

In the branch worktree, restore the base version of every file the branch changed in that area, run the failing file, then restore:

```sh
cd <branch worktree>
git status --porcelain | head -3          # must be clean first
git checkout <base> -- <file1> <file2> <file3>
<test command>                             # expect green
git checkout HEAD -- <file1> <file2> <file3>
git status --porcelain | head -3           # confirm restored
```

Green with base files + red with branch files = the branch caused it. Both red = environment.

## 3. Bisect to one file when the set is larger than two

```sh
for f in <file1> <file2> <file3>; do
  git checkout <base> -- "$f"
  r=$(<test command> 2>&1 | rg -o '[0-9]+ fail' | head -1)
  echo "base $f => $r"
  git checkout HEAD -- "$f"
done
```

The one file whose base version flips the result is the culprit. Restore after every iteration so each run starts from the branch's tree.

## 4. Prove red then green on the real tree

After the fix, capture both numbers on the same worktree, with the fix stashed and restored:

```sh
git stash push -q -- <fixed file>
<test command> | rg -o '[0-9]+ (pass|fail)'   # red
git stash pop -q
<test command> | rg -o '[0-9]+ (pass|fail)'   # green
```

## Pitfalls

- **Do not run the comparison in the main checkout.** Its build artifacts and generated modules go stale and fail to import (`Export named X not found in ...json`), which reads as a branch failure. Compare inside worktrees built from the same sources.
- **An unset env var is not the same as an inactive feature.** Print the resolved value from inside the project (`bun -e 'console.log(process.env.NAME)'`) — shells export values a plain `env | rg` in another process may miss, and `-q` fetches hide failures.
- **The failing assertion's message names the culprit, not the test title.** A generic wrapper error (`Unable to read the selected session.`) means the throw happened earlier than the assertion expected; read the code path that produced it, not the test's intent.
- **REAL root cause may be the environment's configuration interacting with the code.** Both can be true: the code is wrong for a supported configuration, and CI never exercises that configuration. Fix the code, and say in the report which configuration exposes it.
