# Discover the deploy contract

Do not hardcode an org, account, or cluster. Read the repo.

## Where the contract lives

In order, take the first that exists:

1. `.github/workflows/deploy.yml` (or `production.yaml`, `ecs-deploy.yml`)
2. `docs/runbooks/deploying-and-rolling-back.md`
3. `mise` task `deploy` / `deploy-prod`
4. Makefile target the workflow calls

Extract:

| Need              | Typical workflow env / step                                        |
| ----------------- | ------------------------------------------------------------------ |
| Region            | `AWS_REGION` / `aws-region:`                                       |
| Cluster / service | `ECS_CLUSTER`, `ECS_SERVICE`                                       |
| Task family       | `"${CONTAINER_NAME}-${DEPLOY_ENV}"`                                |
| Image repo        | `ECR_REPOSITORY` + login-ecr registry                              |
| Image tag         | `github.sha` → `git rev-parse origin/<default>`                    |
| Controller        | `aws ecs describe-services … deploymentController.type`            |
| CodeDeploy names  | `create-deployment --application-name` / `--deployment-group-name` |
| Container + port  | AppSpec `ContainerName` / `ContainerPort`                          |
| Health URL        | the workflow's `curl` health step                                  |
| Migrate           | `run-task` override `["…/migrate","--up"]` then `--verify`         |
| Build             | `docker build -f …` and any pre-copy of binaries / data            |

`deploymentController.type == CODE_DEPLOY` → you **must** call
`aws deploy create-deployment`. `ECS` → rolling `update-service` is
correct for that repo only.

## Live image vs requested SHA

```bash
aws ecs describe-services --cluster "$CLUSTER" --services "$SERVICE" \
  --query 'services[0].taskDefinition' --output text
aws ecs describe-task-definition --task-definition "$TD" \
  --query 'taskDefinition.containerDefinitions[0].image' --output text
```

Done when that image tag equals the SHA you just pushed.

## Org-agnostic AWS

Use whatever identity `aws sts get-caller-identity` already is — the
operator's profile for that org. Do not assume a role name. The GitHub
OIDC role (`github-actions-deployment`) is for Actions, not laptops.
