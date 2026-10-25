---
name: pending-zyins-changes
description: Check zyins for pending remote rate, plan-name, med, and condition changes via zdrmfmt --sync --force-pull (read-only). Use when the user asks about pending rates, rate drift, zdrmfmt --sync, force-pull, meds/conditions pull, coalesce after pull, or runs /pending-zyins-changes.
---

# Pending zyins changes

Read-only scan of live plan-builder drift vs git. Do not edit zyins from this skill.

## Checkout

Work on `origin/main` in `~/Developer/Software-Automation-Holdings/zyins` or a
worktree under `~/Developer/Software-Automation-Holdings/.worktrees/zyins-*`.
Never the dirty `feat/autonomous-ingestion` checkout.

```bash
cd ~/Developer/Software-Automation-Holdings/zyins
git fetch origin main
wt -C ~/Developer/Software-Automation-Holdings/zyins switch ^ --no-cd --format=json
```

If the default worktree is dirty, `wt switch --create pending-zyins-scan --base origin/main --no-cd --format=json` instead. Set `REPO` below to the JSON `path`.

## Token

```bash
export ZDRMFMT_API_TOKEN="$(
  aws --profile sah --region us-west-2 secretsmanager get-secret-value \
    --secret-id isa-central-api/ZYINS_PLAN_BUILDER_BEARER_TOKEN-prod \
    --query SecretString --output text
)"
```

Do not log the value.

## Read-only scan

Close stdin. `--force-pull` without `--yes` is the dry scan (writes nothing).

Prefer `~/Developer/Software-Automation-Holdings/zyins/bin/zdrmfmt`. Repo-root
`./cmd/zdrmfmt` is wrong. If the worktree must rebuild:

```bash
REPO=<json-path-from-wt-switch>
ZDRMFMT="$REPO/bin/zdrmfmt"
# worktree rebuild only:
# cd "$REPO/go/zyins" && go build -o "$REPO/bin/zdrmfmt" ./cmd/zdrmfmt

</dev/null "$ZDRMFMT" --sync --force-pull
```

## Do not confuse PUSH with pending live rates

`mise run sync-conformance` is PUSH: local `.zdrm` → plan builder. Its FAILED
count is not pending live rates. Skip `plans/test*.zdrm`.

## Classify the scan output

Bucket each hit. Do not mix buckets in the report.

| Bucket                         | What it is                                                                   |
| ------------------------------ | ---------------------------------------------------------------------------- |
| Rate CSVs                      | Diffs under `templates/term/<slug>/csv` and `templates/medsup/<carrier>/csv` |
| Caret-only `additional_checks` | `^` vs `/` only — not a rate change                                          |
| Plan name mismatches           | Display/canonical name drift vs plan builder                                 |
| Meds / conditions              | `additional_checks` for medications or conditions                            |

Lead the report with rate CSVs. Call out caret-only and name mismatches as
non-rate. Meds/conditions last.

## Coalesce is not automatic

`zdrmfmt --force-pull` writes `.zdrm` `additional_checks` from plan builder.
`tools/pipeline/coalesce/reconcile_zdrm_when_fields.py` is a held productgen
step, not a pipeline pass. Do not run it unless the user asks.

## Hard stops

- Do not `--force-pull --yes` without explicit confirmation.
- Do not send Jim / Tyson / Sidman mail.
- Do not add `workflow_dispatch` to Rate go-live.

## After a real pull merges

When a real rate pull lands on `main` touching `templates/**` or `plans/**`,
GitHub Action **Rate go-live** runs `mise run notify-go-live`.

- Recipients: `vars.ZDRMFMT_GO_LIVE_EMAILS`
- Empty `RateWriteFromGitDiff` → send nothing
- CSV charts count; a matching `.zdrm` does not add a chart
- Needs org GitHub secret `RESEND_API_KEY` (repo-level set returns 400)

## Simulate go-live (only if asked)

1. Temporarily set `ZDRMFMT_GO_LIVE_EMAILS` to `zbornheimer@iipgroup.com` only.
2. Push a `templates/term/<slug>/csv/*.csv` change.
3. Watch the Action.
4. Restore the var to `jhiggins@iipgroup.com,zbornheimer@iipgroup.com,btyson@iipgroup.com,msidman@iipgroup.com`.
5. Revert the fake rates.
