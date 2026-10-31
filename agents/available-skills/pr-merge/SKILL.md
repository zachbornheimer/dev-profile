---
name: pr-merge
description: This gives instructions on how to merge PRs that aren't green / clean / an easy way to have a merge happen in the background, resolving issues on its own. Use when a PR was opened and it needs to be merged (it will work on the PR to make it acceptable), if main's CI is red due to a non-billing issue, or if a PR needs to be merged passively.
---

Use the command:
`OMP_REMOTE=1 capability run fix_red_ci < https://github.com/...>` the github.com url should represent either the repo's url to the default branch, to the branch that's red, or to the pr.
