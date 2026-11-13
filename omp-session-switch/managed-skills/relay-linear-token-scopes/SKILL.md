---
name: relay-linear-token-scopes
description: "Before minting a Linear token for the Relay app (client_credentials, op item \"Linear Relay Agent\"), or when Relay suddenly cannot be assigned/delegated in Linear"
---

# Relay Linear token scopes

A Linear `client_credentials` request for the Relay app **replaces the app's scopes and revokes its other app tokens**. Minting with any scope set other than the one relay-edge uses (`cloudflare/relay-edge/worker.mjs` `SCOPES`) drops `app:assignable`, and Relay disappears from Linear's assignee/delegate picker.

Always mint with exactly:

```
grant_type=client_credentials
scope=read,write,app:assignable,app:mentionable
client_id / client_secret = op item "Linear Relay Agent" (vault Zysys), fields "client id" / "client secret"
```

Symptom "I can't assign anything to Relay": re-mint with the scope set above (POST https://api.linear.app/oauth/token). The response `scope` must read `app:assignable app:mentionable read write`. `viewer { name app }` should return `Relay`, `app: true`.

Better: read data through an existing token (Keychain `capability-gateway` / `linear.zys_access_token`) instead of minting a Relay token at all.
