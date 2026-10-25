---
name: find-email-thread
description: Use to search Apple Mail.app for an email thread by subject, sender, or message id — across every account and every mailbox, not just the inbox — then read its full content or save its attachments. Triggers on "search my mail for X", "find that email thread", "when did X email me about Y", "pull the attachment from that email".
---

# find-email-thread — search Apple Mail.app, read content, save attachments safely

## The traps this exists for

1. **Account name != email address.** A Mail.app account's `name` does not
   necessarily match the email address it holds mail for — `zach@zysys.org`'s
   mail can live under an account literally named "Gmail", not "zysys".
   Never guess an account name from an email domain. `search` always walks
   every account.

2. **Inbox alone misses the thread.** Trash, Archive, All Mail, and every
   Gmail label (Mail.app exposes each label as its own mailbox) can hold the
   message you want. `search` always walks every mailbox of every account,
   wrapping each mailbox in its own error handler so one bad mailbox (a smart
   mailbox, a permissions hiccup) doesn't abort the whole account's search.

3. **The attachment-save gotcha — the one destructive failure mode.**
   Mail.app's AppleScript `save a in POSIX file X` treats `X` as the literal
   destination _file_ path, not a directory. Passing a directory path with a
   trailing slash does **not** save into that directory — it silently
   overwrites whatever file (or directory!) already sits at that exact path.
   This has cost a live working directory before. `attachments` always
   builds the full destination path (`out_dir/attachment_name`) before
   calling save, and creates `out_dir` itself with `mkdir -p` in Python
   first — never inside AppleScript.

4. **Message id is the stable handle.** Once `search` finds a match, use its
   `message_id` (and `account`) for follow-up `content`/`attachments` calls —
   never re-search by subject to fetch the body, since subjects aren't
   unique and re-matching can land on a different message in the thread.

## Commands

```bash
# Search — one of --subject / --sender / --msgid, plus optional --json
uv run ~/.agents/available-skills/find-email-thread/scripts/find-email-thread.py \
    search --subject "New Lead" --json

# Full content of one message (message id from a search result)
uv run ~/.agents/available-skills/find-email-thread/scripts/find-email-thread.py \
    content --account "Gmail" --msgid "<abc123@example.com>"

# Save every attachment of one message into a directory (created if missing)
uv run ~/.agents/available-skills/find-email-thread/scripts/find-email-thread.py \
    attachments --account "Gmail" --msgid "<abc123@example.com>" --out /tmp/scratch/attachments
```

`search` output, one line per match (or one JSON object per line with
`--json`): `account`, `mailbox`, `subject`, `sender`, `date_received`,
`message_id`.

Exit codes: `0` with matches printed to stdout; `1` with nothing on stdout
and a diagnostic on stderr when there are zero matches, or when Mail.app
itself errors (e.g. not running, automation permission not granted). Never
prints a path or record that isn't real.

## What this script deliberately doesn't do

It doesn't parse attachment contents (an `.xlsx`, a `.pdf`, an image) — that's
a separate concern. For spreadsheets, use the `xlsx` skill or
`python3 -c "import zipfile..."` against the saved file. This script's job
ends at: find the thread, dump its content, save its attachments correctly.

## Requirements

- Mail.app must be running and have already been granted Automation
  permission for the calling process (System Settings → Privacy & Security →
  Automation). If `osascript` fails, the script surfaces Mail.app's own
  error text on stderr rather than a bare traceback.
- `uv` for `uv run` (the script has no third-party dependencies — PEP 723
  inline metadata declares an empty dependency list, so `uv run` works
  standalone with no separate install step). `python3 scripts/find-email-thread.py`
  also works directly since there's nothing to install.
