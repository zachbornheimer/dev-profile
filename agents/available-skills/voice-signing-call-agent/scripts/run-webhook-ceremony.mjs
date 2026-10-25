#!/usr/bin/env node
/**
 * Mode A — RapidSign voice ceremony via signed Twilio webhooks (no PSTN).
 * Mirrors eapp-system/tests/e2e/rapidsign-demo-voice-live-proof.spec.ts steps.
 *
 * Env:
 *   TWILIO_AUTH_TOKEN or TWILIO_AUTH_TOKEN_FILE (required)
 *   VOICE_CODE (required) — 6-digit mint
 *   CALLER_SPOKEN_NAME (default Jane Doe)
 *   VOICE_WEBHOOK_URL (default prod incoming)
 */
import { createHmac } from 'node:crypto';
import { readFileSync } from 'node:fs';

const VOICE_WEBHOOK_URL =
  process.env.VOICE_WEBHOOK_URL ?? 'https://rapidsign.isaapi.com/v1/voice/incoming';
const DISCLOSURE_CONTINUE_DIGIT = '1';
const COMPLETION_MARKERS = ['signing session is now complete', 'session is now complete'];

function authToken() {
  if (process.env.TWILIO_AUTH_TOKEN) return process.env.TWILIO_AUTH_TOKEN.trim();
  const path = process.env.TWILIO_AUTH_TOKEN_FILE;
  if (!path) throw new Error('Set TWILIO_AUTH_TOKEN or TWILIO_AUTH_TOKEN_FILE');
  return readFileSync(path, 'utf8').trim();
}

function twilioSignature(url, params, token) {
  const sorted = Object.keys(params)
    .sort()
    .map((k) => k + params[k])
    .join('');
  return createHmac('sha1', token)
    .update(url + sorted, 'utf8')
    .digest('base64');
}

async function postSigned(url, params, token) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-Twilio-Signature': twilioSignature(url, params, token),
    },
    body: new URLSearchParams(params).toString(),
  });
  return { status: res.status, body: await res.text() };
}

function steps(callSid, code, name) {
  return [
    { name: 'gather-code-prompt', params: { CallSid: callSid } },
    { name: 'code-entry', params: { CallSid: callSid, Digits: code } },
    { name: 'capture-name-gather', params: { CallSid: callSid } },
    { name: 'disclosure-1', params: { CallSid: callSid, SpeechResult: name } },
    { name: 'disclosure-2', params: { CallSid: callSid, Digits: DISCLOSURE_CONTINUE_DIGIT } },
    { name: 'disclosure-3', params: { CallSid: callSid, Digits: DISCLOSURE_CONTINUE_DIGIT } },
    { name: 'completion', params: { CallSid: callSid, Digits: DISCLOSURE_CONTINUE_DIGIT } },
  ];
}

const code = process.env.VOICE_CODE?.trim();
if (!code) {
  console.error('VOICE_CODE is required');
  process.exit(2);
}
const name = process.env.CALLER_SPOKEN_NAME?.trim() || 'Jane Doe';
const token = authToken();
const callSid = `CAskill${Date.now()}`;

const results = [];
for (const step of steps(callSid, code, name)) {
  const { status, body } = await postSigned(VOICE_WEBHOOK_URL, step.params, token);
  const snippet = body.slice(0, 400);
  results.push({ name: step.name, status, snippet });
  console.log(`[${step.name}] status=${status} body=${snippet.replace(/\s+/g, ' ')}`);
  if (status !== 200) {
    console.error(JSON.stringify({ ok: false, callSid, results }, null, 2));
    process.exit(1);
  }
  const lower = body.toLowerCase();
  if (['expired', 'not recognize', "didn't recognize", 'invalid code'].some((m) => lower.includes(m))) {
    console.error(JSON.stringify({ ok: false, reason: 'code-rejected', callSid, results }, null, 2));
    process.exit(1);
  }
}

const last = results[results.length - 1]?.snippet?.toLowerCase() ?? '';
const complete = COMPLETION_MARKERS.some((m) => last.includes(m));
console.log(JSON.stringify({ ok: complete, callSid, complete, results }, null, 2));
process.exit(complete ? 0 : 1);
