---
name: enrich-contact
description: Use when user says 'enrich contact X', '/enrich-contact', 'find a photo + tag for X', 'fill in X's contact', or wants to batch-enrich a Contacts group — adds tag, website, headshot to macOS Contacts.
user-invokable: true
disable-model-invocation: false
argument-hint: "[contact name | group:GroupName]"
---

# enrich-contact

Fill in a contact with only what is **actionable**: an instrument tag, a verified website, a good photo. Nothing for the sake of it — no role/bio scrapes. The bar for every output is "would Zach keep it," not "did I find something."

<principles>
  - **Actionable only.** Instrument tag (you'll ask "who plays drums?"), tappable website, recognizable photo. If a field doesn't help *recall* or *reach* someone, skip it.
  - **Good photo or none.** A bad photo (blurry, wrong person, instrument across the face, harsh stage light, mouthpiece-in-mouth) is worse than no photo — it pops up on every call. Skip rather than settle.
  - **Verify, never claim.** A 200 status is not a real website. An agent saying "set + verified" is not proof. The main thread VIEWS the photo and re-queries the card before anything is considered done.
  - **Reversible.** Tags are groups; photos/URLs are removable. Show before applying when identity is ambiguous.
</principles>

## Special cases (handle BEFORE the normal pipeline)

- **Deceased.** Don't auto-mark someone deceased from a web hit — it may be a namesake (the Henry Ashwood _Sr._ who died 2000 vs the living _Jr._), and the stakes of getting it wrong are awful. If research strongly suggests a death, **stop and flag it to the owner** — don't mark it yourself. When the owner confirms: add to an **"In Memoriam"** group, **remove from "Archive · 1yr+ no contact"** (that group is about reconnecting — the wrong frame), keep/enrich the photo + instrument tag (still true, aids memory), and **never delete**.
- **Not a person (iMessage / service entries).** Shortcodes (e.g. `893-32`), automated senders, no-reply/unsubscribe addresses, group-chat handles, carrier/customer-service numbers — these aren't people. No photo, no instrument tag, no website, no invented identity. Leave them, or route to a **Junk · Review** group. (A _business_ with a real brand is different — that gets logo-as-photo + website; see business mode.)

## Architecture (this is the point of the skill)

The main thread orchestrates and **verifies**; a **fresh-context subagent does the discovery + apply** (the main thread accumulates history that shouldn't color a clean pass). For a single contact, one subagent. For a group, fan out one subagent per contact (cap concurrency ~6) and verify each result.

1. Resolve the target(s): a name, or `group:GroupName` → every member.
2. **Skip the already-reviewed** (see _Review stamp_). For a group run, read each member's `auto-reviewed` stamp first; skip those reviewed inside the freshness window unless the user said "re-run" / "force". This is what makes a group run resumable — re-invoking after a crash picks up where it stopped instead of re-paying for done cards.
3. Spawn a `general-purpose` subagent per remaining contact with the prompt below (inherit the session model — capable models do photo judgment; cheap ones lie about it).
4. **Main-thread verify** each returned result: `Read` the final image to confirm it's good + the right person, and re-query the card (`image present`, `in instrument group`, `urls`). Only then is it done. If the photo fails your eye, pull it.
5. **Stamp it reviewed** (see _Review stamp_) — _after_ verification, success or deliberate no-op alike. The stamp records that the main thread looked at this card on this date; it is not the subagent's claim. A card left intentionally untagged (a non-musician, a service entry) still gets stamped — "reviewed, nothing to add" is a finished state, not a gap.

## The tool — `contactctl`

All reads and writes go through a Swift CLI bundled with this skill:

```text
contactctl   # /Users/zbornheimer/.local/bin/contactctl, source at ~/Zysys/Software/contactctl
```

It talks to the native Contacts framework (`CNContactStore`) — **not** AppleScript / AppleEvents — so every reliability problem the old workflow ran into is gone: photos persist without the PNG-roundtrip dance, custom dates upsert without the `-10000` delete bug, group writes are atomic, and the binary holds its own stable Contacts permission instead of riding on the host app's evaporating AppleEvents one. Every command prints a single JSON value so the orchestrator (and any subagent) can parse the result without scraping prose.

```text
contactctl get        <id>                  # full card as JSON
contactctl find       <name>                # name → [{id, name}]
contactctl unreviewed <letter>              # cards by surname-initial with no review stamp
contactctl members    <group>               # everyone in a group, with stamp state
contactctl reviewed   <id>                  # the auto-reviewed date, or null
contactctl tag        <id> <group>          # add to a Contacts group (creates it if missing)
contactctl untag      <id> <group>
contactctl url        <id> <label> <value>  # add a URL (idempotent on value)
contactctl email      <id> <label> <value>  # add an email (idempotent on value)
contactctl photo      <id> <imagePath>      # set the photo; persists reliably
contactctl rmphoto    <id>
contactctl stamp      <id> [YYYY-MM-DD]     # upsert the auto-reviewed date
contactctl friend-photo <name> [path]       # find the owner's FB friend by name, grab their photo (namesake-proof)
contactctl get-profile-picture <fbURL> [path]  # grab a FB photo from a profile/photo/CDN URL you already have
```

`<id>` accepts either a bare `CNContact` UUID or the AppleScript form `<uuid>:ABPerson` — both resolve. First invocation prompts once in System Settings ▸ Privacy & Security ▸ Contacts; later runs need no prompt.

If the binary is missing, rebuild with `make -C ~/Zysys/Software/contactctl install`. The source lives at `~/Zysys/Software/contactctl` (git-tracked separately); only the install symlink lives on `$PATH`.

## Review stamp

A custom date labelled **`auto-reviewed`** records the last main-thread review. It is the idempotency key for group runs and the resume cursor for the whole project. Set by the **main thread only**, after verification — never by a subagent.

```text
contactctl reviewed <id>                    # print the date, or null
contactctl stamp    <id>                    # upsert (today by default)
```

## The subagent prompt (per contact)

> Enrich the macOS Contacts entry for **<NAME>**. Use **every field on the card** to identify the right person, then add an instrument tag, a verified website, and a GOOD photo. Be honest — the parent re-verifies your photo.
>
> **You are the subagent. Don't call `contactctl stamp` or touch the `auto-reviewed` custom date in any way — that stamp belongs to the parent and is set only after it verifies your work.** Even if your card-state check shows it's missing, even if you'd "complete the workflow," even if it'd make the task feel finished — _do not stamp_. The parent will catch unstamped work and stamp after eye-checking. Ignore the _Review stamp_ section of this skill entirely; it documents an API you must not invoke. Don't add a job title, department, or any field beyond tag / website / photo unless this prompt explicitly asks.
>
> **1. Read the WHOLE card** with `contactctl get <ID>`. The JSON includes first/middle/last/nickname/prefix/suffix, organization, job title, department, every phone, email, url, postal address, dates, group memberships, and `image: true/false`. Mine ALL of it for identity clues, not just the name:
>
> - area code → region; email handle often leaks the instrument (`kaxsax` → sax) or employer (domain);
> - **org, job title, related names, address, and dates are frequently the deciding clue** for a common name — read them. (The card's free-form `note` is restricted by macOS entitlements and is not in the JSON; if the parent gave you the note text, use it.)
>
> **2. Identify + corroborate** via web (try the browser first — ToolSearch `mcp__claude-in-chrome__tabs_context_mcp,navigate,computer,javascript_tool`; if unavailable, DuckDuckGo headless: vqd token from `duckduckgo.com/?q=Q&iax=images&ia=images`, then `duckduckgo.com/i.js?l=us-en&o=json&q=Q&vqd=TOKEN&f=,,,&p=1`). Cross-check against the card's clues. If the card contradicts your candidate, reconsider. If you can't confirm, STOP and report — never guess a stranger onto the card.
>
> **3. Capability tag** — `contactctl tag <ID> "<Group>"` (creates the group if missing). Plain names: Drums, Sax, Piano, Bass, Trumpet, Guitar, Vocals, Trombone… **Tags = music CAPABILITIES: instruments AND non-playing music functions** — `Sound Engineer`, `Producer`, `Composer/Arranger`, `Band Director`, `Booking Agent`. The test: would the owner search _"who can \_\_\_ for me?"_ — a thing they'd call/hire this person _for_. **Don't tag an AFFILIATION or job** — employer / school / firm / location (e.g. "North Broward Prep", "USF", a law firm). Someone with no music capability (a teacher, lawyer, gym trainer, admissions officer) simply gets **no tag** — that's correct, not a gap to fill. Only tag a capability you've CONFIRMED.
>
> **4. Website** — only if real AND verified theirs. Probe likely domains; `curl -sL -A '<browser UA>' URL` and check the title/content is actually them, NOT parked/squatted/gambling (a 200 means nothing). Add with `contactctl url <ID> homepage https://…` (idempotent on value). Skip if none.
>
> **5. Photo — the test is RECOGNITION, not polish.** The job of a contact photo is to help the owner _distinguish this person at a glance_. So the bar is "can you tell who this is," not "is it a studio headshot."
>
> - **Try the owner's Facebook friends list FIRST: `contactctl friend-photo "<name>" /tmp/<slug>_fb.jpg`.** It searches the owner's _own friends_ by name (surname-first) and grabs that friend's profile photo — identity-verified by the friend graph, so zero namesake risk, and it's usually the best forward-facing shot. `{"ok":true,...}` means it saved a file → `Read` it, and if it's a group/couple shot, crop the contact out (you have their face from the friend match). `{"ok":false,...}` just means they're not a findable friend — fall through to the sources below. (It needs the owner's Chrome logged into Facebook; a `reason` mentioning identity means Chrome is acting as the wrong profile — report it, don't retry.)
> - **Otherwise check the professional page.** A bio / faculty / artist / law-firm / press page (the same one you used to confirm identity) is the BEST non-FB source — attributed to exactly this person, forward-facing, clean. Grab it (`curl` the page, find the portrait `<img>`, often named `Lastname_First...jpg`) BEFORE image search, which skews to action shots. Do NOT discard a bio-page photo on a name-based gender assumption ("Peri", "Adrian", "Sasha" can be any gender) — if it's on their own page, it's them.
> - **A performance / casual / older / B&W shot is GOOD ENOUGH and beats no photo when the face reads clearly.** A musician with their instrument _in frame_ is fine, even helpful for recall. If a tight face crop is awkward (mouthpiece at the mouth, harsh stage light), **pull the frame back to head-and-shoulders** rather than rejecting it.
> - **Reject ONLY when the photo fails recognition:** the face is obscured (instrument/hand/mic across the face), it's too dark/blurry/low-res to tell who it is, it's a group shot you can't isolate them from, or it's the wrong person. A recognizable imperfect photo > a "pretty" unrecognizable one > nothing. Search (browser Google Images `...&udm=2`, or DDG fallback) → `curl` the highest-res real file → **`Read` it to confirm quality + identity** → crop a clean square centered on the face with headroom (`sips -c H W --cropOffset top left`) → `Read` the crop → re-crop if clipped/off; **if a tight face crop looks awkward, pull back to include more frame** (for performance-only people, the instrument in frame is fine). Save as `/tmp/<slug>_final.jpg` (`sips -s format jpeg -Z 512`).
> - **Set the photo** with `contactctl photo <ID> /tmp/<slug>_final.jpg`. It persists reliably — no PNG roundtrip needed, no separate verify session needed (the old AppleScript silent-drop bug is fixed at the API level). The command prints `"image": true` on success.
> - No headshot clears the bar → set NO photo, say so. Leave the final at `/tmp/<slug>_final.jpg` for the parent's eye-check.
>
> **Report:** identity + corroborating sources + confidence; which card fields drove the ID; instrument tag(s); website (added/skipped + why); photo (source URL, honest quality read, set y/n, file path). A wrong/bad photo is worse than none.

## Main-thread verification (do not skip)

For each subagent result: `Read /tmp/<slug>_final.jpg` (is it genuinely good + the right person?) and re-query the card with `contactctl get <ID>` to confirm `image: true`, the expected `groups`, and new `urls`. Subagents have falsely claimed "set + verified." Trust nothing unseen. Report to the user only what you confirmed; for ambiguous identity, show a candidate sheet and let them pick.

## Notes

- iCloud is the single contacts source; groups sync to iPhone as Lists.
- Removing later: `contactctl rmphoto <ID>` · `contactctl untag <ID> "<Group>"`. URL removal isn't yet in the CLI — edit the card in Contacts.app for that one case.
- `contactctl` requires Contacts access in System Settings ▸ Privacy & Security ▸ Contacts (granted to itself, separately from Terminal/Claude).
