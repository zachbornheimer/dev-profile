#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Search Apple Mail.app for a thread, dump its content, and save attachments.

Usage:
    find-email-thread.py search --subject TEXT [--json]
    find-email-thread.py search --sender TEXT [--json]
    find-email-thread.py search --msgid TEXT [--json]
    find-email-thread.py content --account NAME --msgid ID
    find-email-thread.py attachments --account NAME --msgid ID --out DIR

All Mail.app interaction goes through `osascript` (AppleScript) via
subprocess — there is no first-class Python Mail.app binding worth adding
as a dependency, and AppleScript is the only interface Mail.app exposes for
per-mailbox message search.

Three traps this script exists to avoid (see SKILL.md for the full story):

1. An account's `name` in Mail.app does NOT necessarily match the email
   address it holds mail for (a Gmail account named "Gmail" can hold
   zach@zysys.org's mail). Never assume account name from email domain —
   `search` always walks every account.

2. Inbox alone misses mail filed elsewhere (Trash, Archive, All Mail, and
   every Gmail label, which Mail.app exposes as a separate mailbox).
   `search` always walks every mailbox of every account.

3. Mail.app's `save a in POSIX file X` treats X as the literal destination
   FILE path, not a directory — passing a directory path with a trailing
   slash does NOT save into that directory, it overwrites whatever file (or
   directory!) sits at that exact path. `attachments` always builds the
   full destination path (directory + attachment filename) before saving.

Search terms and message ids are passed into AppleScript string literals
after escaping backslashes and double quotes, so a term containing a quote
can't break out of the string or inject additional AppleScript.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

OSASCRIPT_TIMEOUT_SECONDS = 60


def escape_applescript_string(value: str) -> str:
    """Escapes a value for embedding inside a double-quoted AppleScript
    string literal, so search terms/ids containing a quote or backslash
    can't break out of the literal or inject AppleScript."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def run_applescript(script: str) -> str:
    """Runs an AppleScript via osascript and returns stdout, stripped.
    Raises RuntimeError with osascript's stderr on non-zero exit, so
    callers get Mail.app's own error text rather than a bare traceback."""
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=OSASCRIPT_TIMEOUT_SECONDS,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"osascript failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


# AppleScript's `text item delimiters` trick is used to build one output
# record per matching message, joined by a delimiter unlikely to appear in
# any field, then split back into Python records.
FIELD_SEP = "\u001f"  # unit separator
RECORD_SEP = "\u001e"  # record separator


def build_search_script(field_name: str, term: str) -> str:
    """field_name is "subject", "sender", or "message id" — the AppleScript
    property being matched with `contains` (message id uses `is` for an
    exact match instead, via build_msgid_search_script)."""
    escaped = escape_applescript_string(term)
    return f'''
    tell application "Mail"
        set outputList to {{}}
        repeat with acc in every account
            set accName to name of acc
            try
                repeat with mb in every mailbox of acc
                    try
                        set theMessages to (messages of mb whose {field_name} contains "{escaped}")
                        repeat with m in theMessages
                            try
                                set rec to accName & "{FIELD_SEP}" & (name of mb) & "{FIELD_SEP}" & (subject of m as string) & "{FIELD_SEP}" & (sender of m as string) & "{FIELD_SEP}" & (date received of m as string) & "{FIELD_SEP}" & (message id of m as string)
                                set end of outputList to rec
                            end try
                        end repeat
                    end try
                end repeat
            end try
        end repeat
        set AppleScript's text item delimiters to "{RECORD_SEP}"
        set outputString to outputList as string
        set AppleScript's text item delimiters to ""
        return outputString
    end tell
    '''


def build_msgid_search_script(msgid: str) -> str:
    escaped = escape_applescript_string(msgid)
    return f'''
    tell application "Mail"
        set outputList to {{}}
        repeat with acc in every account
            set accName to name of acc
            try
                repeat with mb in every mailbox of acc
                    try
                        set theMessages to (messages of mb whose message id is "{escaped}")
                        repeat with m in theMessages
                            try
                                set rec to accName & "{FIELD_SEP}" & (name of mb) & "{FIELD_SEP}" & (subject of m as string) & "{FIELD_SEP}" & (sender of m as string) & "{FIELD_SEP}" & (date received of m as string) & "{FIELD_SEP}" & (message id of m as string)
                                set end of outputList to rec
                            end try
                        end repeat
                    end try
                end repeat
            end try
        end repeat
        set AppleScript's text item delimiters to "{RECORD_SEP}"
        set outputString to outputList as string
        set AppleScript's text item delimiters to ""
        return outputString
    end tell
    '''


def parse_records(raw: str) -> list[dict]:
    if not raw:
        return []
    records = []
    for chunk in raw.split(RECORD_SEP):
        if not chunk:
            continue
        parts = chunk.split(FIELD_SEP)
        if len(parts) != 6:
            continue
        account, mailbox, subject, sender, date_received, message_id = parts
        records.append(
            {
                "account": account,
                "mailbox": mailbox,
                "subject": subject,
                "sender": sender,
                "date_received": date_received,
                "message_id": message_id,
            }
        )
    return records


def cmd_search(args: argparse.Namespace) -> int:
    if args.msgid is not None:
        script = build_msgid_search_script(args.msgid)
        term_desc = f"message id '{args.msgid}'"
    elif args.subject is not None:
        script = build_search_script("subject", args.subject)
        term_desc = f"subject containing '{args.subject}'"
    else:
        script = build_search_script("sender", args.sender)
        term_desc = f"sender containing '{args.sender}'"

    raw = run_applescript(script)
    records = parse_records(raw)

    if not records:
        print(f"No messages matched {term_desc}.", file=sys.stderr)
        return 1

    for rec in records:
        if args.json:
            print(json.dumps(rec))
        else:
            print(
                f"{rec['account']} / {rec['mailbox']} | {rec['subject']} | "
                f"{rec['sender']} | {rec['date_received']} | "
                f"msgid:{rec['message_id']}"
            )
    print(f"{len(records)} match(es)", file=sys.stderr)
    return 0


def build_content_script(account: str, msgid: str) -> str:
    escaped_account = escape_applescript_string(account)
    escaped_msgid = escape_applescript_string(msgid)
    return f'''
    tell application "Mail"
        repeat with mb in every mailbox of account "{escaped_account}"
            try
                set theMsgs to (messages of mb whose message id is "{escaped_msgid}")
                if (count of theMsgs) > 0 then
                    return content of (item 1 of theMsgs) as string
                end if
            end try
        end repeat
        return ""
    end tell
    '''


def cmd_content(args: argparse.Namespace) -> int:
    script = build_content_script(args.account, args.msgid)
    body = run_applescript(script)
    if not body:
        print(
            f"No message with id '{args.msgid}' found in account '{args.account}'.",
            file=sys.stderr,
        )
        return 1
    print(body)
    return 0


def build_attachments_script(account: str, msgid: str, out_dir: str) -> str:
    """Saves every attachment of the matched message into out_dir.

    Builds the FULL destination path (out_dir + attachment name) before
    calling `save`, since `save a in POSIX file X` treats X as the literal
    destination file, not a directory — a bare directory path with a
    trailing slash silently overwrites whatever sits at that exact path
    instead of saving into it. out_dir itself is created by the caller
    (mkdir -p) before this script runs, not by AppleScript.
    """
    escaped_account = escape_applescript_string(account)
    escaped_msgid = escape_applescript_string(msgid)
    escaped_dir = escape_applescript_string(out_dir.rstrip("/"))
    return f'''
    tell application "Mail"
        repeat with mb in every mailbox of account "{escaped_account}"
            try
                set theMsgs to (messages of mb whose message id is "{escaped_msgid}")
                if (count of theMsgs) > 0 then
                    set theMsg to item 1 of theMsgs
                    set savedNames to {{}}
                    repeat with a in mail attachments of theMsg
                        set attName to name of a
                        set destPath to "{escaped_dir}/" & attName
                        save a in POSIX file destPath
                        set end of savedNames to attName
                    end repeat
                    set AppleScript's text item delimiters to "{RECORD_SEP}"
                    set outputString to savedNames as string
                    set AppleScript's text item delimiters to ""
                    return outputString
                end if
            end try
        end repeat
        return ""
    end tell
    '''


def cmd_attachments(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    script = build_attachments_script(args.account, args.msgid, str(out_dir))
    raw = run_applescript(script)

    if not raw:
        print(
            f"No message with id '{args.msgid}' found in account "
            f"'{args.account}', or it has no attachments.",
            file=sys.stderr,
        )
        return 1

    names = [n for n in raw.split(RECORD_SEP) if n]
    for name in names:
        print(str(out_dir / name))
    print(f"Saved {len(names)} attachment(s) to {out_dir}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search Apple Mail.app across all accounts/mailboxes, "
        "dump message content, and save attachments safely."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser(
        "search", help="Search every mailbox of every account"
    )
    term_group = search_parser.add_mutually_exclusive_group(required=True)
    term_group.add_argument("--subject", help="Subject substring to match")
    term_group.add_argument("--sender", help="Sender substring to match")
    term_group.add_argument("--msgid", help="Exact message id to match")
    search_parser.add_argument(
        "--json", action="store_true", help="Print one JSON object per match"
    )
    search_parser.set_defaults(func=cmd_search)

    content_parser = subparsers.add_parser(
        "content", help="Print the full content of one message"
    )
    content_parser.add_argument("--account", required=True)
    content_parser.add_argument("--msgid", required=True)
    content_parser.set_defaults(func=cmd_content)

    attachments_parser = subparsers.add_parser(
        "attachments", help="Save every attachment of one message"
    )
    attachments_parser.add_argument("--account", required=True)
    attachments_parser.add_argument("--msgid", required=True)
    attachments_parser.add_argument(
        "--out", required=True, help="Directory to save attachments into"
    )
    attachments_parser.set_defaults(func=cmd_attachments)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
