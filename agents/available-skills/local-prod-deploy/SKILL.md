---
name: local-prod-deploy
description: Use when GitHub Actions (or the repo's CI deploy) cannot start and production still needs the SHA already on the default branch — "Actions is blocked", "deploy from this laptop", spending-limit / startup_failure on Deploy, or any org whose CI runners are down. Do not use for a normal green-CI deploy (use deploy).
---

# Local prod deploy (CI blocked)

Laptop is a **stand-in runner**, not a new pipeline. Replay the repo's Deploy
workflow against the same AWS account. Inventing `ecs update-service
--force-new-deployment` is the default mistake — many services use a
`CODE_DEPLOY` controller and that command is rejected or silent-no-op.

Load `deploy` for canary / health / rollback rules. This skill only covers
the "Actions cannot start" path.

## Gates (fail closed)

1. **Actions is actually blocked.** Latest Deploy (or the org's equivalent)
   is `startup_failure` / spending-limit / no jobs. If a runner can start,
   dispatch the workflow instead.
2. **SHA is already on `origin/<default>`.** Dirty tree, a feature branch,
   or a SHA that is not an ancestor of the default branch → stop.
3. **Replay the workflow.** Read `.github/workflows/deploy.yml` (or the
   file `mise` / the Makefile names). Same image tag (the git SHA), same
   migrate-then-cutover order, same health URL. Skip only jobs whose
   **diff vs the live image SHA** does not touch that artifact.
4. **Cross-compile.** A Mac `go build` is `darwin/*`. Production Linux
   images need `GOOS=linux GOARCH=<task-def-arch>` (zyins: `arm64`).
5. **Don't skip migrate / verify / canary / health** because you are local.
6. **Quote image tags as `"${IMAGE}:${TAG}"`.** `"$IMAGE:latest"` can be
   parsed as a bash substring and push to a garbage repo name.

Scripts (run; don't re-derive):

```bash
# Confirm the tree is shippable and Actions is dead
~/.agents/available-skills/local-prod-deploy/scripts/preflight.sh --repo /path/to/repo

# After the image is in ECR — ECS + CodeDeploy cutover only
~/.agents/available-skills/local-prod-deploy/scripts/ecs-codedeploy-cutover.sh --help
```

How to read a repo's contract: `references/discover.md`.

## After cutover

Same bar as `deploy`: tail logs ≥ 2 min, hit the workflow's health URL,
spot-check the changed endpoint, then watch the canary window. Rollback
through **CodeDeploy**, not `update-service`.
