#!/usr/bin/env bash
# Load RapidSign voice secrets into the current shell (source this file).
# Requires AWS profile sah (aws-vault credential_process) or AWS_PROFILE set.
set -euo pipefail

PROFILE="${AWS_PROFILE:-sah}"
export AWS_PROFILE="$PROFILE"

# Preview secrets exist in the sah account used for local agent work.
# Set TWILIO_SID_SECRET / TWILIO_TOKEN_SECRET to prod names when in prod account.
SID_SECRET="${TWILIO_SID_SECRET:-rapidsign/twilio-account-sid-preview}"
TOKEN_SECRET="${TWILIO_TOKEN_SECRET:-rapidsign/twilio-auth-token-preview}"
XAI_SECRET="${XAI_SECRET_ID:-rapidsign/xai-api-key}"

need() {
  local name="$1" id="$2"
  local val
  val="$(aws secretsmanager get-secret-value --secret-id "$id" --query SecretString --output text)"
  if [[ -z "$val" || "$val" == "PLACEHOLDER" ]]; then
    echo "fetch-secrets: $name from $id is empty or PLACEHOLDER" >&2
    return 1
  fi
  printf -v "$name" "%s" "$val"
  export "$name"
}

need XAI_API_KEY "$XAI_SECRET"
need TWILIO_ACCOUNT_SID "$SID_SECRET"
need TWILIO_AUTH_TOKEN "$TOKEN_SECRET"

umask 077
TOKEN_FILE="${TWILIO_AUTH_TOKEN_FILE:-/tmp/twilio-auth-token}"
printf "%s" "$TWILIO_AUTH_TOKEN" > "$TOKEN_FILE"
export TWILIO_AUTH_TOKEN_FILE="$TOKEN_FILE"

echo "fetch-secrets: loaded XAI_API_KEY + Twilio (profile=$PROFILE sid=$SID_SECRET); token file=$TOKEN_FILE" >&2
