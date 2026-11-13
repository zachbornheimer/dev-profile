---
name: everest-voice-sign-tts-routing
description: "Where Everest voice-sign script text and TTS voice (Grok vs Polly/Twilio) are defined, and why a long static disclosure may play in the Twilio voice"
---

# Everest voice-sign: script and TTS routing

## Where things live
- Script text: `zyins/products/everest-cancer-concierge/critical-illness/tuning.yaml` ~lines 726-770, `signature_settings.signers.*` / `voice_script` (steps: press-1 confirm with {{signer.name}}, ACKNOWLEDGMENT, BANKING AUTHORIZATION with effective_date + payment.mode placeholders, capture-name prompt). Disclosure text is carrier/CEO-approved legal wording: do not edit without user sign-off.
- TTS ladder: `rapidsign/internal/handler/voice_prompt_audio.go` `synthesizePromptAudio`: cache -> Grok (`voicePromptSynthesisTimeout = 3s`, line ~67) -> Polly fallback.
- Twilio voice heard on fallback: `rapidsign/internal/handler/twiml.go:79` `ceremonyTTSVoice = "Polly.Joanna-Neural"`.
- Cache/personal gate: `voice_prompt_facade.go` `promptSpeechFacade`. A step is "personal" (never cached, never prerendered, synthesized live every call) if the script flag is set, it has unresolved `{{placeholders}}`, or `mayCacheStep` (voice_webhook.go:415, `state.MayCacheSpokenText`) says no.

## Gotcha (inference, not verified from call logs)
`voice_script.has_personal_info: true` makes every step non-cacheable, including the static ACKNOWLEDGMENT. Long live synthesis can exceed Grok's 3s budget and drop to Polly, so the user hears the Twilio voice. Fix options: make static steps cacheable/prerendered, raise the timeout for long steps, or split long text. Check call logs (`rapidsign.voice.tts.synthesis` source = grok/polly-fallback) before asserting the cause.

## Related
- Voice e2e harness: skill `voice-signing-call-agent`; IVR narration is ~42.5s per gate, so default 8 gate presses at 4s are dropped (use PAUSE_BEFORE_GATE_PRESSES=2 GATE_PRESS_INTERVAL=5 GATE_PRESS_COUNT=60 PAUSE_TAIL=20).
- Banking authorization wording reads oddly for a non-payor signer; options proposed: lead-in for account owner (A) or payor/non-payor variants (B, needs a form signal).
