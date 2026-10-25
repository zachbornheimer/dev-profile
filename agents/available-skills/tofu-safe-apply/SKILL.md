---
name: tofu-safe-apply
description: Use when asked to "tofu apply if safe", "safe apply", "tofu plan and apply", or any variant of "plan this and apply it if it's safe" against an OpenTofu/Terraform working dir. Encodes Zach's evidenced safety boundary as a deterministic script — never re-derive the classification by eye.
---

# Tofu Safe Apply

Zach has asked "tofu plan and if safe, apply" across many repos. The boundary of
"safe" is evidenced, not a judgment call to remake each time — it is encoded once
in `scripts/tofu-safe-apply.sh` and run the same way everywhere.

**Always run the script. Never hand-classify a plan and apply based on your own
read of it** — the script is the single source of truth for this decision, and an
agent's read of a plan is exactly the class of mistake this skill exists to
prevent.

## How to use it

```sh
~/.agents/available-skills/tofu-safe-apply/scripts/tofu-safe-apply.sh [dir] [--dry-run] [--allow-branch]
```

- `[dir]` — the OpenTofu working directory (defaults to `.`).
- `--dry-run` — classify and print the verdict, never apply.
- `--allow-branch` — explicit override for the branch/clean/up-to-date preflight
  (see below). Never pass this on the user's behalf without them asking for it —
  it is the one lever that weakens the "apply only from merged main" rule.

Exit code is `0` for SAFE (applied, unless `--dry-run`) or NONE (no changes), `1`
for UNSAFE (nothing applied) or a refused preflight.

### Testing the classifier without a tofu backend

```sh
~/.agents/available-skills/tofu-safe-apply/scripts/tofu-safe-apply.sh --classify-only <plan.json>
```

Reads a saved `tofu show -json` plan document directly — this is how
`scripts/test-classify.sh` drives the fixtures under `scripts/fixtures/`, and how
you should validate a change to the classifier before trusting it live.

## Preflight refusals (checked before any plan runs)

| Refusal                                                                                              | Reason                                                                                                                        |
| ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Current branch isn't `main`/`master`                                                                 | "apply only from merged main" — override with `--allow-branch`                                                                |
| Working tree is dirty                                                                                | uncommitted changes must not be applied silently — override with `--allow-branch`                                             |
| Branch is behind its upstream                                                                        | stale branch could apply a plan against outdated state — override with `--allow-branch`                                       |
| A `*.tfvars`/`*.tfvars.example` exists but nothing auto-loads (`terraform.tfvars` / `*.auto.tfvars`) | a plan run without its var-file has, in a real incident, invented catastrophic false destroys — names the specific file found |

## Classification table (every resource change)

| Change                                                   | Verdict | Why                                                       |
| -------------------------------------------------------- | ------- | --------------------------------------------------------- |
| no-op / read                                             | SAFE    | nothing changing                                          |
| create                                                   | SAFE    | additive                                                  |
| in-place update                                          | SAFE    | no resource is destroyed                                  |
| replace, `create_before_destroy`                         | SAFE    | "create before destroy is okay"                           |
| replace, destroy-before-create                           | UNSAFE  | destroys before the replacement exists                    |
| delete                                                   | UNSAFE  | destructive by definition                                 |
| **any** change to a protected type, even in-place update | UNSAFE  | "not idiot-proof" — never auto-apply regardless of action |

Protected types (regex, matched on resource `type`): `aws_kms_*`, `aws_iam_*`,
`*_grant`, `aws_dynamodb_table`, `aws_s3_bucket` (the bucket resource itself —
`aws_s3_bucket_*` attachments are not protected), `aws_rds_*`, `aws_db_*`.

## The rule that never bends

**UNSAFE always stops for Zach.** The script prints the full change table with
every offending row marked, followed by `STOPPED — needs Zach:` and a per-row
reason, then exits 1 without applying. No flag, no re-run, and no agent judgment
overrides an UNSAFE verdict — if the situation is genuinely fine despite the
verdict (e.g. an intentional IAM change), that decision is Zach's to make by
reviewing the table and applying manually, not the agent's to make on his behalf.
