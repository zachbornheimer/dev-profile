# The carry list

The only manifest is `.fork/branches` on default branch `fork`. It contains one topic branch per line, in the order CI must merge them:

```text
fix/first
feat/second
```

Blank lines and comment lines beginning with `#` are ignored. Each entry names a pushed topic cut from the pristine upstream mirror. Keep topics independent and upstream-PR-ready; ordering is not permission to hide another topic in a branch.

Use the fork tool to register changes and drop absorbed carries. Do not maintain another manifest or edit generated assembly branches. Exact commands and rerere conflict handling belong to `shipping-a-fork-binary-via-mise`.
