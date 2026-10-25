#!/usr/bin/env bash
# tofu-safe-apply.sh — plan an OpenTofu working dir, classify every resource
# change against Zach's evidenced safety boundary, and apply only when every
# change classifies SAFE. UNSAFE verdicts always stop for a human; nothing in
# this script can be told to override that classification.
#
# Usage:
#   tofu-safe-apply.sh [dir] [--dry-run] [--allow-branch]
#   tofu-safe-apply.sh --classify-only <plan.json> [--dry-run]
set -euo pipefail

readonly PROG_NAME="tofu-safe-apply"

# --- protected resource types -------------------------------------------
# Zach's rule: any change to these, even in-place, is never auto-applied.
# shellcheck disable=SC2016 # jq source literal — $type/$rc are jq variables, not shell
readonly PROTECTED_TYPE_JQ='
def is_protected($type):
  ($type | test("^aws_kms_")) or
  ($type | test("^aws_iam_")) or
  ($type | test("_grant$")) or
  ($type == "aws_dynamodb_table") or
  ($type == "aws_s3_bucket") or
  ($type | test("^aws_rds_")) or
  ($type | test("^aws_db_"));
'

die() {
	printf 'refusing to apply: %s\n' "$1" >&2
	exit 1
}

info() {
	printf '%s\n' "$1"
}

usage() {
	cat <<EOF
Usage: ${PROG_NAME}.sh [dir] [--dry-run] [--allow-branch]
       ${PROG_NAME}.sh --classify-only <plan.json> [--dry-run]
EOF
}

# --- preflight: apply only from merged main -----------------------------
# Zach's rule: apply only from a clean, up-to-date main/master. --allow-branch
# is the one explicit override; nothing else bypasses this gate.
preflight_git_state() {
	local will_apply="${3:-false}"
	local working_dir="$1"
	local allow_branch="$2"

	if ! git -C "$working_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
		return 0 # not a git repo — nothing to enforce
	fi

	local branch
	branch=$(git -C "$working_dir" rev-parse --abbrev-ref HEAD)
	if [[ "$branch" != "main" && "$branch" != "master" ]]; then
		if [[ "$allow_branch" == true ]]; then
			info "WARNING: applying from branch '${branch}', not main/master (--allow-branch)."
		else
			die "current branch '${branch}' is not main/master (apply only from merged main). Re-run with --allow-branch to override."
		fi
	fi

	if [[ -n "$(git -C "$working_dir" status --porcelain)" ]]; then
		if [[ "$allow_branch" == true ]]; then
			info "WARNING: working tree is dirty (--allow-branch)."
		else
			die "working tree is dirty (uncommitted changes). Re-run with --allow-branch to override."
		fi
	fi

	local upstream
	if upstream=$(git -C "$working_dir" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null); then
		if [[ "$will_apply" == true ]]; then
			# A real apply deserves a fresh view of origin; a stale ref could
			# pass a branch that merged main has since moved past.
			git -C "$working_dir" fetch --quiet "${upstream%%/*}" 2>/dev/null ||
				info "WARNING: could not fetch ${upstream%%/*}; behind-origin check uses last-fetched state."
		fi
		local behind_count
		behind_count=$(git -C "$working_dir" rev-list --count "HEAD..${upstream}")
		if [[ "$behind_count" -gt 0 ]]; then
			if [[ "$allow_branch" == true ]]; then
				info "WARNING: branch is ${behind_count} commit(s) behind ${upstream} (--allow-branch)."
			else
				die "branch is ${behind_count} commit(s) behind ${upstream} (apply only when up to date with origin). Re-run with --allow-branch to override."
			fi
		fi
	fi
}

# --- preflight: refuse a plan that would run without its var-file --------
# Real incident: a plan run without the intended var-file invented
# catastrophic false destroys. If a *.tfvars / *.tfvars.example sits in the
# dir but nothing auto-loads (terraform.tfvars or *.auto.tfvars), stop.
preflight_var_file_safety() {
	local working_dir="$1"

	local auto_loaded=false
	[[ -e "${working_dir}/terraform.tfvars" ]] && auto_loaded=true
	if compgen -G "${working_dir}/*.auto.tfvars" >/dev/null 2>&1; then
		auto_loaded=true
	fi
	[[ "$auto_loaded" == true ]] && return 0

	local flagged=()
	local file
	if compgen -G "${working_dir}/*.tfvars" >/dev/null 2>&1; then
		for file in "${working_dir}"/*.tfvars; do
			[[ "$(basename "$file")" == "terraform.tfvars" ]] && continue
			[[ "$file" == *.auto.tfvars ]] && continue
			flagged+=("$(basename "$file")")
		done
	fi
	if compgen -G "${working_dir}/*.tfvars.example" >/dev/null 2>&1; then
		for file in "${working_dir}"/*.tfvars.example; do
			flagged+=("$(basename "$file")")
		done
	fi

	if [[ "${#flagged[@]}" -gt 0 ]]; then
		die "found $(
			IFS=', '
			echo "${flagged[*]}"
		) but no terraform.tfvars/*.auto.tfvars will be auto-loaded — a plan without its var-file can invent catastrophic false destroys. Pass -var-file explicitly or add an auto-loaded file."
	fi
}

# --- plan + classify ------------------------------------------------------
run_tofu_plan() {
	local working_dir="$1"
	local plan_file="$2"
	local plan_exit=0
	tofu -chdir="$working_dir" plan -detailed-exitcode -out="$plan_file" >&2 || plan_exit=$?
	if [[ "$plan_exit" -eq 1 ]]; then
		die "tofu plan failed"
	fi
	echo "$plan_exit"
}

plan_to_json() {
	local working_dir="$1"
	local plan_file="$2"
	local json_file="$3"
	tofu -chdir="$working_dir" show -json "$plan_file" >"$json_file"
}

classify_plan_json() {
	local json_file="$1"
	jq -c "${PROTECTED_TYPE_JQ}"'
[.resource_changes[]? |
  . as $rc |
  ($rc.change.actions) as $actions |
  ($actions | join(",")) as $actionstr |
  if ($actions == ["no-op"]) or ($actions == ["read"]) then
    {address: $rc.address, type: $rc.type, name: $rc.name, actions: $actionstr, verdict: "SAFE", reason: "no-op"}
  elif is_protected($rc.type) then
    {address: $rc.address, type: $rc.type, name: $rc.name, actions: $actionstr, verdict: "UNSAFE", reason: "protected resource type (\($rc.type)) — never auto-apply"}
  elif $actions == ["delete"] then
    {address: $rc.address, type: $rc.type, name: $rc.name, actions: $actionstr, verdict: "UNSAFE", reason: "delete"}
  elif $actions == ["delete","create"] then
    {address: $rc.address, type: $rc.type, name: $rc.name, actions: $actionstr, verdict: "UNSAFE", reason: "replace is destroy-before-create"}
  else
    {address: $rc.address, type: $rc.type, name: $rc.name, actions: $actionstr, verdict: "SAFE",
     reason: (if $actions == ["create","delete"] then "replace create_before_destroy" else $actionstr end)}
  end
]' "$json_file"
}

# --- reporting -------------------------------------------------------------
print_change_table() {
	local rows_json="$1"
	printf '%-8s %-9s %-40s %-30s %s\n' "VERDICT" "ACTION" "TYPE" "NAME" "REASON"
	jq -r '.[] | [.verdict, .actions, .type, .name, .reason] | @tsv' <<<"$rows_json" |
		while IFS=$'\t' read -r verdict actions type name reason; do
			printf '%-8s %-9s %-40s %-30s %s\n' "$verdict" "$actions" "$type" "$name" "$reason"
		done
}

overall_verdict() {
	local rows_json="$1"
	local row_count unsafe_count
	row_count=$(jq 'length' <<<"$rows_json")
	if [[ "$row_count" -eq 0 ]]; then
		echo "NONE"
		return
	fi
	unsafe_count=$(jq '[.[] | select(.verdict == "UNSAFE")] | length' <<<"$rows_json")
	if [[ "$unsafe_count" -gt 0 ]]; then
		echo "UNSAFE"
	else
		echo "SAFE"
	fi
}

report_and_exit() {
	local rows_json="$1"
	local verdict
	verdict=$(overall_verdict "$rows_json")

	case "$verdict" in
	NONE)
		info "No changes. Nothing to apply."
		echo "NONE"
		return 0
		;;
	SAFE)
		print_change_table "$rows_json"
		echo "SAFE"
		return 0
		;;
	UNSAFE)
		print_change_table "$rows_json"
		info ""
		info "STOPPED — needs Zach:"
		jq -r '.[] | select(.verdict == "UNSAFE") | "  - \(.address): \(.reason)"' <<<"$rows_json"
		echo "UNSAFE"
		return 1
		;;
	esac
}

# --- modes -----------------------------------------------------------------
run_classify_only() {
	local json_file="$1"
	local rows_json
	rows_json=$(classify_plan_json "$json_file")
	report_and_exit "$rows_json"
}

run_plan_and_apply() {
	local working_dir="$1"
	local allow_branch="$2"
	local dry_run="$3"

	local will_apply=true
	[[ "$dry_run" == true ]] && will_apply=false
	preflight_git_state "$working_dir" "$allow_branch" "$will_apply"
	preflight_var_file_safety "$working_dir"

	local plan_file json_file
	plan_file=$(mktemp)
	json_file=$(mktemp)
	trap 'rm -f "$plan_file" "$json_file"' EXIT

	local plan_exit
	plan_exit=$(run_tofu_plan "$working_dir" "$plan_file")
	if [[ "$plan_exit" -eq 0 ]]; then
		info "No changes. Nothing to apply."
		return 0
	fi

	plan_to_json "$working_dir" "$plan_file" "$json_file"
	local rows_json
	rows_json=$(classify_plan_json "$json_file")

	local verdict
	verdict=$(overall_verdict "$rows_json")

	local report_exit=0
	report_and_exit "$rows_json" || report_exit=$?
	if [[ "$verdict" == "UNSAFE" ]]; then
		return "$report_exit"
	fi

	if [[ "$verdict" == "SAFE" && "$dry_run" != true ]]; then
		info ""
		info "Applying saved plan..."
		tofu -chdir="$working_dir" apply "$plan_file"
	fi
}

main() {
	local working_dir="."
	local allow_branch=false
	local dry_run=false
	local classify_only_file=""

	while [[ $# -gt 0 ]]; do
		case "$1" in
		--dry-run)
			dry_run=true
			shift
			;;
		--allow-branch)
			allow_branch=true
			shift
			;;
		--classify-only)
			classify_only_file="$2"
			shift 2
			;;
		-h | --help)
			usage
			exit 0
			;;
		*)
			working_dir="$1"
			shift
			;;
		esac
	done

	if [[ -n "$classify_only_file" ]]; then
		run_classify_only "$classify_only_file"
		exit $?
	fi

	run_plan_and_apply "$working_dir" "$allow_branch" "$dry_run"
}

main "$@"
