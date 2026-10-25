# Privacy

**Check:** No mounted capability measures this yet: report it as unmeasured, never healthy. Intended scope (trackers and cookies observed, consent behavior, privacy policy diff, script inventory on payment pages).

## Facts and limits (this is monitoring, not legal advice)
- About 20 US states have comprehensive privacy laws; nonprofit exemptions vary by state, so applicability for ISJAC must be confirmed by counsel.
- 11 states require honoring Global Privacy Control (GPC). The check verifies GPC turns off sale/share trackers where required.
- PCI: SAQ A dropped requirements 6.4.3 and 11.6.1 in 2025 but added an eligibility criterion that payment page scripts be secure. Keep the script inventory on donate/checkout pages small and known.

## Checks
- Diff observed trackers and cookies against what the privacy policy declares; an undeclared tracker is a finding.
- Consent banner: no non-essential tags before consent; withdrawal works.
- Payment pages: list every third-party script; a new one is a finding.
- Policy has a review date within 12 months.

**Triage:** undeclared tracker means remove it or update the policy (the policy text is the client's, drafted with counsel; ask). GPC failure: fix tag firing.

**Needs Zach:** policy wording; any legal interpretation goes to counsel via the client.

**Common misses:** analytics or pixel added by a plugin update; embedded videos and maps setting cookies; consent banner blocking nothing.

**Cadence:** trackers monthly; policy review yearly.
