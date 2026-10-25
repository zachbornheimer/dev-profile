---
name: voice-signing-call-agent
description: >-
  Repeatable RapidSign / Everest voice IVR call-in harness: mint a call-in
  code, complete the ceremony (DTMF + spoken name), using Twilio webhook
  simulation or a real outbound PSTN call. Loads Grok (xAI) API key via AWS
  profile sah / Secrets Manager (rapidsign/xai-api-key). Use when an agent
  must call in, listen, and speak for voice signing — not for SMS/email sign.
---

# Voice signing call agent

Fixed outer workflow (design-harness): **mint → secrets → drive ceremony →
poll/hangup**. Generative nodes are bounded (spoken name / disclosure
interpretation only). Do not free-agent the telephony loop.

## When to use

- Everest / RapidSign **Sign over the phone** on eApp (local or live).
- Agent must complete call-in without a human dialing.
- Debugging voice-sign ceremonies against `rapidsign.isaapi.com`.

## Defaults (org truth)

| Item | Value |
|------|--------|
| Call-in number | `+1 (272) 770-3377` → E.164 `+12727703377` (`DEFAULT_VOICE_SIGN_PHONE_NUMBER` in eapp `isa-sdk.js`) |
| Voice webhook | `https://rapidsign.isaapi.com/v1/voice/incoming` |
| Telephony | **Twilio** (not Connect/Chime) — see `infra/environments/prod/rapidsign/README.md` |
| xAI / Grok key secret | `rapidsign/xai-api-key` |
| Twilio secrets | Preview (this account): `rapidsign/twilio-account-sid-preview`, `rapidsign/twilio-auth-token-preview`. Prod names (other account): `rapidsign/twilio-account-sid`, `rapidsign/twilio-auth-token` |
| AWS profile | `sah` (`credential_process = aws-vault export --format=json sah`) |
| Proven e2e sim | `eapp-system/tests/e2e/rapidsign-demo-voice-live-proof.spec.ts` |

## Modes

| Mode | What it does | Prefer when |
|------|----------------|-------------|
| **A — Webhook ceremony** | POSTs signed Twilio webhooks (code DTMF → speak name → press 1 ×3). No PSTN. | Agents, CI, local proof. **Default.** |
| **B — Twilio outbound** | Real `Calls.create` to `+12727703377` with scripted TwiML (`Pause` / `Play digits` / `Say`). | Need a real CallSid / carrier path. |
| **C — Grok voice realtime** | `wss://api.x.ai/v1/realtime` (+ optional SIP). | Adaptive listen/speak; needs public webhook or Media Streams bridge. |

Search before inventing: Twilio is already the voice path. Do not add Connect/Chime unless Twilio is unavailable.

---

## 0. Prerequisites

```bash
# Unlock vault once per shell session if needed
aws-vault exec sah -- aws sts get-caller-identity

# Or use the profile directly (credential_process)
aws --profile sah sts get-caller-identity
```

Node 20+ for skill scripts. No extra npm deps for Mode A/B.

---

## 1. Fetch secrets (AWS + Grok / Bedrock-adjacent)

Bedrock is **not** where the Grok API key lives for RapidSign — **Secrets Manager**
is (`rapidsign/xai-api-key`). Use AWS profile `sah` / aws-vault. (Bedrock may
still be used for other AWS TTS; voice signing’s LLM key is xAI / Grok.)

```bash
export AWS_PROFILE=sah
# or: aws-vault exec sah -- bash

export XAI_API_KEY="$(aws secretsmanager get-secret-value \
  --secret-id rapidsign/xai-api-key \
  --query SecretString --output text)"

# Prefer preview secrets in account 514598028285; override with prod IDs when in prod account
export TWILIO_ACCOUNT_SID="$(aws secretsmanager get-secret-value \
  --secret-id "${TWILIO_SID_SECRET:-rapidsign/twilio-account-sid-preview}" \
  --query SecretString --output text)"

export TWILIO_AUTH_TOKEN="$(aws secretsmanager get-secret-value \
  --secret-id "${TWILIO_TOKEN_SECRET:-rapidsign/twilio-auth-token-preview}" \
  --query SecretString --output text)"

# Never echo these. Optional file for Playwright live-proof:
umask 077
printf '%s' "$TWILIO_AUTH_TOKEN" > /tmp/twilio-auth-token
export TWILIO_AUTH_TOKEN_FILE=/tmp/twilio-auth-token
```

Helper (same commands):

```bash
source ~/.cursor/skills/voice-signing-call-agent/scripts/fetch-secrets.sh
```

Preview Twilio secrets use `…-preview` suffix — see
`infra/environments/preview/rapidsign/README.md`.

---

## 2. Mint a call-in code (eApp)

**Local Everest (this machine’s form):**

```text
http://localhost:8000/form/cancer-concierge-simplified-issue-application/bb3ecbf0-910d-4152-a160-9893313df65e/?skip_landing#0
```

Worktree serving `:8000`:
`~/Developer/Software-Automation-Holdings/.worktrees/eapp-system-form-builder-edit-surface`

Walk to RapidSign → **Sign over the phone** → **Get call-in code**. Capture the
6-digit code shown in the UI (and keep the page open so polling can finish).

**Live demo mint (no local stack):**

```bash
cd ~/Developer/Software-Automation-Holdings/eapp-system
EAPP_RUN_RAPIDSIGN_VOICE_MINT=1 PLAYWRIGHT_SKIP_WEBSERVER=1 \
  npx playwright test tests/e2e/rapidsign-demo-voice-mint-walk.spec.ts \
    --project=chromium --workers=1
```

Docs: `eapp-system/docs/voice-sign-local-testing.md`.

---

## 3. Drive the ceremony

### Mode A — webhook simulation (default)

```bash
export VOICE_CODE='123456'          # minted code
export CALLER_SPOKEN_NAME='Jane Doe'
# TWILIO_AUTH_TOKEN already set from §1

node ~/.cursor/skills/voice-signing-call-agent/scripts/run-webhook-ceremony.mjs
```

Ceremony order (live IVR, 2026-09-29; source of truth is rapidsign
`internal/handler/twiml.go` `actionToTwiML` + `internal/documents/ceremony.go`):

1. Code gather: `Gather dtmf finishOnKey=# timeout=10` (send `<code>#`; no speech)
2. Preparing: `preparing.mp3` (1.9s, "Pulling up your application now.") + `typing-sounds.mp3`
   once (1.1s) = a fixed 3.0s, + `Redirect` (was ~18s before rapidsign PR #1262 / #1263 on 2026-09-30)
3. Opener: `<Start><Recording channels=dual>` + `Gather dtmf speech numDigits=1 speechTimeout=auto`
   with `opener.mp3` — say the name here. The dual-channel recording starts now.
4. Name confirm: `Gather dtmf speech numDigits=1` with `capture-name-confirm.mp3` — press 1
5. Script gates: each `say` step plays its narration OUTSIDE the Gather (DTMF during it is
   dropped), then `Gather dtmf numDigits=1 timeout=5` with `gate.mp3` — press 1. Anything
   else repeats the step. A script `capture-name` step is skipped (the opener captured it).
6. Goodbye: `goodbye.mp3` + `Hangup`. The recording lands via `/voice/recording` after hangup.

A `1` that reaches the opener Gather before the name costs a name retry, so never press
early. Mode A sends the same sequence as webhooks.

### Mode B — real outbound PSTN (Twilio)

Needs a Twilio **From** number on the same account as the auth token:

```bash
export TWILIO_FROM='+1XXXXXXXXXX'   # Twilio number you own
export VOICE_IVR_TO='+12727703377'
export VOICE_CODE='123456'
export CALLER_SPOKEN_NAME='Jane Doe'

node ~/.cursor/skills/voice-signing-call-agent/scripts/run-outbound-twilio.mjs call
```

Subcommands: `call` (default) places the call, waits for it to end (~55s), finds the
IVR's inbound leg, and downloads its recording to `RECORDING_OUT_DIR`; `recording`
refetches for `OUTBOUND_CALL_SID`; `twiml` prints the TwiML with no network (check it
before every dial). Stdout is one JSON line: `callSid`, `inboundLegSid`, `recording`,
`reachedGoodbye`, `capturedSpeech`, `codeToNamePromptMs`, and the leg's webhook
`timeline` from Twilio call events.

Timeline sent (seconds): pause 5 → `<code>#` → pause 10 (resolve ~1.5 + preparing/typing 3.0 +
redirect ~0.3 + opener 5.1) →
say name → pause 5 → `1` (name confirm) → pause 4 → eight `1` presses 4s apart (script
gates; early presses are dropped or repeat a step) → pause 20 → hangup. Tune with
`PAUSE_BEFORE_CODE`, `PAUSE_BEFORE_NAME`, `PAUSE_BEFORE_NAME_CONFIRM`,
`PAUSE_BEFORE_GATE_PRESSES`, `GATE_PRESS_INTERVAL`, `GATE_PRESS_COUNT`, `PAUSE_TAIL`, or
replace it wholesale with `TWIML_OVERRIDE_FILE`. On a misfire (`reachedGoodbye: false`),
read `timeline.steps` to see which Gather got the wrong input before re-dialing.

**No recording MP3 until hangup + recording-status callback.** The recording lives on
the IVR's inbound leg (a different CallSid from the one you placed).
eapp-system `tests/e2e/everest/support/transcribe.sh <mp3>` runs whisper per channel.

### Mode C — Grok voice (bounded generative)

```bash
# After XAI_API_KEY is set (from AWS above):
# Docs: https://docs.x.ai/ — Speech to Speech / SIP / Bedrock is not the key store
# WebSocket: wss://api.x.ai/v1/realtime
# SIP inbound: register phone via POST /v2/phone-numbers, handle
#   realtime.call.incoming, then join wss://api.x.ai/v1/realtime?call_id=...
```

For RapidSign **outbound** into `+12727703377`, prefer Mode B TwiML or a Twilio
Media Streams bridge into Grok realtime. xAI SIP is primarily **inbound to
Grok**. Session instructions should be the fixed ceremony script in
`references/ceremony-script.md` — do not invent new IVR steps.

Org Playwright live-proof (Mode A against prod + mint):

```bash
cd ~/Developer/Software-Automation-Holdings/eapp-system
EAPP_RUN_RAPIDSIGN_VOICE_LIVE_PROOF=1 PLAYWRIGHT_SKIP_WEBSERVER=1 \
  TWILIO_AUTH_TOKEN_FILE=/tmp/twilio-auth-token \
  npx playwright test tests/e2e/rapidsign-demo-voice-live-proof.spec.ts \
    --project=chromium --workers=1
```

---

## 4. Gates / failure modes

| Symptom | Action |
|---------|--------|
| `403` on webhook | Wrong/missing `TWILIO_AUTH_TOKEN`; signature mismatch |
| “expired” / “not recognize” | Re-mint code (30 min TTL); retry once |
| `502` on mint via proxy | Upstream rapidsign voice-code — infra, not eapp client |
| No signature on page | Keep form open; poll ~5s; ensure ceremony reached completion TwiML |
| No MP3 | Expected until hangup + `/v1/voice/recording` callback |
| Secrets `PLACEHOLDER` | Rotate `rapidsign/xai-api-key` out-of-band; flip `xai_secret_rotated` in Terraform when wiring Lambda |

Human gate: only approve Mode B/C against **prod** IVR when intentional (real carrier cost + live signing).

---

## 5. Harness shape (fixed graph)

```text
[Mint code] → [Load secrets] → [Mode A|B|C] → [Assert completion TwiML / UI signature]
                                      ↑
                         generative only inside spoken-name / Grok session
```

Idempotent: each Mode A run uses a fresh synthetic `CallSid`. Re-run after
re-mint; do not reuse an expired code.

---

## Paths

| Path | Role |
|------|------|
| `~/.cursor/skills/voice-signing-call-agent/SKILL.md` | This skill |
| `…/scripts/fetch-secrets.sh` | AWS → env |
| `…/scripts/run-webhook-ceremony.mjs` | Mode A |
| `…/scripts/run-outbound-twilio.mjs` | Mode B (`call` / `recording` / `twiml`) |
| `…/references/ceremony-script.md` | IVR script for Grok / humans |
