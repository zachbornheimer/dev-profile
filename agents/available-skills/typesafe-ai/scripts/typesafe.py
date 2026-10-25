#!/usr/bin/env python3
"""TypeSafe CLI: pick a skill, judge an agent's final turn, or classify mail, tickets, on-call,
findings, and files; fail open."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TextIO

import catalog
import clarity_judge
import classify
import classify_file
import classify_isjac
import classify_oncall
import classify_ticket
import pick
import rerank
import systemone
import taxonomy
import taxonomy_classify
import turn_judge
from constants import (
    API_KEY_ENV,
    KEYCHAIN_SERVICE,
    REASON_RERANK_FAILED,
    REASON_UNAVAILABLE,
    TURN_JUDGE_REQUEST_TIMEOUT_SECONDS,
)
from systemone import Getenv, JudgmentError, ReadKeychain, Urlopen

GATES = {
    "classify-isjac": classify_isjac,
    "classify-ticket": classify_ticket,
    "classify-oncall": classify_oncall,
}


def home_dir(getenv: Getenv) -> Path:
    raw = getenv("HOME")
    return Path(raw) if raw else Path.home()


def emit_json(payload: Any, stdout: TextIO) -> None:
    json.dump(payload, stdout, ensure_ascii=False)
    stdout.write("\n")


def observe_key(
    getenv: Getenv,
    read_keychain: ReadKeychain | None,
) -> str | None:
    if read_keychain is not None:
        return systemone.resolve_api_key(getenv, read_keychain)

    def from_keychain() -> str | None:
        return systemone.default_read_keychain(getenv)

    return systemone.resolve_api_key(getenv, from_keychain)


ReadText = Callable[[str], str | None]


def read_skill_text(path: str) -> str | None:
    if not path:
        return None
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def pick_skill(
    prompt: str,
    *,
    getenv: Getenv,
    urlopen: Urlopen | None,
    read_keychain: ReadKeychain | None,
    skills: list[catalog.Skill] | None,
    in_flight: str = "",
    context: dict[str, Any] | None = None,
    read_text: ReadText = read_skill_text,
) -> pick.PickResult:
    """Wide rank + needs-skill gate, then a rerank of the shortlist (TypeSafe cookbook)."""
    roster = skills if skills is not None else catalog.scan_skills(home_dir(getenv))
    roster = catalog.collapse_roster(roster)
    key = observe_key(getenv, read_keychain)
    if not key:
        return pick.local_pick(prompt, roster, systemone.missing_key_error().reason)
    request = pick.build_request(prompt, roster, in_flight, context)
    try:
        reply = systemone.ask(
            request,
            key,
            getenv=getenv,
            urlopen=urlopen,
            adapt=lambda base, payload: pick.for_base(payload, roster, base),
        )
        wide = pick.read_wide(
            reply["answers"],
            roster,
            reply.get("usage"),
            in_flight,
            has_context=bool(
                context and (context.get("current_task") or context.get("durable_project_context"))
            ),
        )
    except (JudgmentError, ValueError, TypeError, KeyError) as exc:
        reason = exc.reason if isinstance(exc, JudgmentError) else pick.fallback().reason
        return pick.local_pick(prompt, roster, reason)
    settled = pick.gate(wide, roster)
    if settled is not None:
        return settled
    return _rerank(request["state"], wide, roster, key, getenv, urlopen, read_text)


def _rerank(
    state: dict[str, Any],
    wide: pick.Wide,
    roster: list[catalog.Skill],
    key: str,
    getenv: Getenv,
    urlopen: Urlopen | None,
    read_text: ReadText,
) -> pick.PickResult:
    """A failed rerank suggests nothing: the top of the rank never had its fit check."""
    by_name = {skill.name: skill for skill in roster}
    names = wide.shortlist()
    shortlist = [by_name[name] for name in names]
    texts = {skill.name: read_text(skill.path) for skill in shortlist}
    request = rerank.build_request(state, shortlist, texts)
    try:
        reply = systemone.ask(request, key, getenv=getenv, urlopen=urlopen)
        choice, confidence, fits = rerank.decide(reply["answers"], names)
    except (JudgmentError, ValueError, TypeError, KeyError) as exc:
        detail = exc.reason if isinstance(exc, JudgmentError) else type(exc).__name__
        return pick.result(wide, roster, f"{REASON_RERANK_FAILED}: {detail}")
    return pick.settle(wide, roster, choice, confidence, fits)


def _with_timeout(urlopen: Urlopen | None, timeout: float) -> Urlopen:
    """``urlopen`` with its timeout replaced: judge-turn waits longer than pick-skill."""
    opener = urlopen if urlopen is not None else urllib.request.urlopen

    def open_with_timeout(request: Any, **_kwargs: Any) -> Any:
        return opener(request, timeout=timeout)

    return open_with_timeout


def judge_clarity(
    raw: str,
    *,
    getenv: Getenv,
    urlopen: Urlopen | None,
    read_keychain: ReadKeychain | None,
) -> clarity_judge.ClarityVerdict:
    try:
        state = clarity_judge.load_state(raw)
    except (ValueError, TypeError) as exc:
        return clarity_judge.fallback(f"{REASON_UNAVAILABLE}: {exc}")
    if not state["prose"]:
        return clarity_judge.fallback(clarity_judge.REASON_NO_PROSE)
    key = observe_key(getenv, read_keychain)
    if not key:
        return clarity_judge.fallback(systemone.missing_key_error().reason)
    try:
        result = systemone.ask(
            clarity_judge.build_request(state),
            key,
            getenv=getenv,
            urlopen=_with_timeout(urlopen, 15.0),
        )
        return clarity_judge.decide(result["answers"], state, result.get("usage"))
    except JudgmentError as exc:
        return clarity_judge.fallback(exc.reason)
    except (ValueError, TypeError, KeyError) as exc:
        return clarity_judge.fallback(f"{REASON_UNAVAILABLE}: {exc}")


def judge_turn(
    raw: str,
    *,
    getenv: Getenv,
    urlopen: Urlopen | None,
    read_keychain: ReadKeychain | None,
) -> turn_judge.TurnVerdict:
    key = observe_key(getenv, read_keychain)
    if not key:
        return turn_judge.fallback(systemone.missing_key_error().reason)
    try:
        envelope = turn_judge.load_envelope(raw)
        result = systemone.ask(
            turn_judge.build_request(envelope),
            key,
            getenv=getenv,
            urlopen=_with_timeout(urlopen, TURN_JUDGE_REQUEST_TIMEOUT_SECONDS),
        )
        return turn_judge.decide_turn(
            result["answers"],
            envelope.get("evidence") or {},
            result.get("usage"),
            user_request=str(envelope.get("user_prompt") or ""),
        )
    except JudgmentError as exc:
        return turn_judge.fallback(exc.reason, exc.hops)
    except (ValueError, TypeError, KeyError) as exc:
        return turn_judge.fallback(f"{turn_judge.fallback().reason}: {exc}")


def judge_or_fallback(
    raw: str,
    gate: Any,
    *,
    getenv: Getenv,
    urlopen: Urlopen | None,
    read_keychain: ReadKeychain | None,
) -> Any:
    if not raw.strip():
        return gate.fallback()
    key = observe_key(getenv, read_keychain)
    if not key:
        return gate.fallback(systemone.missing_key_error().reason)
    try:
        state = gate.load_state(raw)
        result = systemone.ask(
            gate.build_request(state),
            key,
            getenv=getenv,
            urlopen=urlopen,
        )
        return gate.decide(result["answers"], state, result.get("usage"))
    except (JudgmentError, ValueError, TypeError, KeyError) as exc:
        reason = exc.reason if isinstance(exc, JudgmentError) else gate.fallback().reason
        return gate.fallback(reason)


def classify_findings(
    raw: str,
    *,
    getenv: Getenv,
    urlopen: Urlopen | None,
    read_keychain: ReadKeychain | None,
) -> list[dict[str, Any]]:
    try:
        findings, tickets = classify.load_payload(raw)
    except (TypeError, ValueError):
        return []
    api_key = observe_key(getenv, read_keychain)
    classified: list[dict[str, Any]] = []
    for finding in findings:
        if api_key is None or not classify.should_classify(finding):
            classified.append(classify.stamp_fallback(finding))
            continue
        request = classify.build_request(finding, tickets)
        try:
            result = systemone.ask(request, api_key, getenv=getenv, urlopen=urlopen)
            classified.append(classify.apply_answers(finding, result["answers"], tickets))
        except (JudgmentError, ValueError, TypeError, KeyError):
            api_key = None
            classified.append(classify.stamp_fallback(finding))
    return classified


def load_taxonomy_or_none(path: str) -> taxonomy.Taxonomy | None:
    """Load and validate `taxonomy.json`; any I/O or schema problem falls open to
    None (design section 1.2) so `classify_files` can fall back to flat mode with
    `REASON_FILE_TAXONOMY_INVALID` instead of ever raising past this point."""
    if not path:
        return None
    try:
        return taxonomy.load_taxonomy(path)
    except (OSError, ValueError, TypeError):
        return None


def classify_files(
    paths: Sequence[str],
    catalog_entries: list[dict[str, Any]],
    linear_projects: list[dict[str, Any]],
    *,
    getenv: Getenv,
    urlopen: Urlopen | None,
    read_keychain: ReadKeychain | None,
    taxonomy_path: str = "",
) -> list[classify_file.FileResult | taxonomy_classify.TaxonomyFileResult]:
    # An invalid/missing --taxonomy falls open to None here, which the loop below
    # already treats as "run flat mode" (design section 1.2's fallback contract) —
    # no separate error path needed.
    file_taxonomy = load_taxonomy_or_none(taxonomy_path)
    results: list[classify_file.FileResult | taxonomy_classify.TaxonomyFileResult] = []
    api_key = observe_key(getenv, read_keychain)
    for raw_path in paths:
        try:
            observation = classify_file.observe(Path(raw_path))
        except FileNotFoundError:
            results.append(classify_file.fallback(raw_path, "path not found"))
            continue
        prefiltered = classify_file.prefilter(observation)
        if prefiltered is not None:
            results.append(prefiltered)
            continue
        if api_key is None:
            results.append(classify_file.fallback(observation["path"]))
            continue
        if file_taxonomy is not None:
            try:
                results.append(
                    _classify_one_taxonomy(observation, file_taxonomy, api_key, getenv, urlopen)
                )
            except (JudgmentError, ValueError, TypeError, KeyError) as exc:
                api_key = None
                reason = (
                    exc.reason
                    if isinstance(exc, JudgmentError)
                    else classify_file.REASON_UNAVAILABLE
                )
                results.append(_taxonomy_fallback(observation["path"], file_taxonomy, reason))
            continue
        # One batched call (typesafe-skills rule 4): a deterministic shortlist decides
        # what to ask about, not what to answer — `strong_project_match` pre-empts the
        # project questions only when the filename makes it unambiguous; otherwise the
        # shortlist's per-candidate relevance Nouls, plus kind/disposition Choice, ride
        # in the same request. Disposition legality is enforced in decide() afterward.
        strong_match = classify_file.strong_project_match(observation, catalog_entries)
        try:
            request = classify_file.build_request(
                observation, catalog_entries, linear_projects, project=strong_match
            )
            response = systemone.ask(request, api_key, getenv=getenv, urlopen=urlopen)
            results.append(
                classify_file.decide(
                    response["answers"],
                    observation,
                    catalog_entries,
                    linear_projects,
                    project=strong_match,
                )
            )
        except (JudgmentError, ValueError, TypeError, KeyError) as exc:
            api_key = None
            if isinstance(exc, JudgmentError):
                results.append(classify_file.fallback(observation["path"], exc.reason))
            else:
                results.append(classify_file.fallback(observation["path"]))
    return results


def _classify_one_taxonomy(
    observation: dict[str, Any],
    file_taxonomy: taxonomy.Taxonomy,
    api_key: str,
    getenv: Getenv,
    urlopen: Urlopen | None,
) -> taxonomy_classify.TaxonomyFileResult:
    """The `--taxonomy` path for one file: `taxonomy_classify.classify` drives up to
    `FILE_TAXONOMY_MAX_ROUNDS` batched calls through the injected `ask` facade.
    Judgment/protocol failures propagate to the caller, which applies the same
    give-up-on-this-key policy flat mode uses for the rest of the run."""

    def ask(request: dict[str, Any]) -> dict[str, Any]:
        request = {"model": classify_file.MODEL, **request}
        response = systemone.ask(request, api_key, getenv=getenv, urlopen=urlopen)
        return response["answers"]

    return taxonomy_classify.classify(observation, file_taxonomy, ask)


def _taxonomy_fallback(
    path: str, file_taxonomy: taxonomy.Taxonomy, reason: str
) -> taxonomy_classify.TaxonomyFileResult:
    return taxonomy_classify.TaxonomyFileResult(
        file=classify_file.fallback(path, reason),
        node=None,
        tree_path=(),
        resolved_depth=0,
        path_score=0.0,
        edges=(),
        alternates=(),
        rounds=0,
        taxonomy_version=file_taxonomy.taxonomy_version,
    )


def install_key(getenv: Getenv, stdout: TextIO) -> int:
    secret = getenv(API_KEY_ENV)
    if secret is None or not secret.strip():
        print(f"set {API_KEY_ENV} before install-key", file=sys.stderr)
        return 1
    account = getenv("USER") or ""
    if not account:
        print("USER is unset; cannot write keychain", file=sys.stderr)
        return 1
    try:
        systemone.write_generic_password(account, KEYCHAIN_SERVICE, secret.strip())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"stored {KEYCHAIN_SERVICE} in login keychain", file=stdout)
    return 0


def add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Write JSON (always on).")


def interrogate(
    raw: str, *, getenv: Getenv, urlopen: Urlopen | None, read_keychain: ReadKeychain | None
) -> dict[str, Any]:
    request = json.loads(raw or "{}")
    if (
        not isinstance(request, dict)
        or not request.get("conversation")
        or not request.get("questions")
    ):
        raise ValueError("interrogate requires conversation and questions")
    questions = {}
    for index, question in enumerate(request["questions"], start=1):
        if not isinstance(question, dict):
            raise TypeError("interrogate questions must be objects")
        questions[f"question_{index}"] = question
    key = observe_key(getenv, read_keychain)
    if not key:
        raise systemone.missing_key_error()
    result = systemone.ask(
        {
            "model": "gpt-5",
            "state": {
                "conversation": request["conversation"],
                "context": request.get("context", {}),
            },
            "questions": questions,
        },
        key,
        getenv=getenv,
        urlopen=urlopen,
    )
    return {"answers": result["answers"], "usage": result.get("usage", {}), "source": "typesafe"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Pick a skill or classify mail, tickets, on-call, findings, and files with "
            "TypeSafe. Fail open."
        )
    )
    sub = parser.add_subparsers(dest="command")
    pick_parser = sub.add_parser("pick-skill", help="Choose at most one skill for a prompt.")
    pick_parser.add_argument("--prompt", required=True, help="User prompt to route.")
    pick_parser.add_argument(
        "--in-flight",
        default="",
        help="Work already in progress in this session (empty means none).",
    )
    pick_parser.add_argument(
        "--context",
        default="",
        help="Bounded JSON context about the current session.",
    )
    add_json_flag(pick_parser)
    classify_parser = sub.add_parser(
        "classify-findings",
        help="Stamp harness-efficiency findings with TypeSafe action and primitive.",
    )
    add_json_flag(classify_parser)
    interrogate_parser = sub.add_parser(
        "interrogate", help="Answer a typed question set about a conversation."
    )
    add_json_flag(interrogate_parser)
    classify_file_parser = sub.add_parser(
        "classify-file",
        help="Identify which project a loose file belongs to and what should happen to it.",
    )
    classify_file_parser.add_argument(
        "paths", nargs="+", help="One or more file or directory paths to classify."
    )
    classify_file_parser.add_argument(
        "--catalog",
        default="",
        help="Path to a repo-catalog.json (optional; project=none when absent).",
    )
    classify_file_parser.add_argument(
        "--linear-projects",
        default="",
        help="Inline JSON list of Linear project names (optional).",
    )
    classify_file_parser.add_argument(
        "--taxonomy",
        default="",
        help="Path to a taxonomy.json for hierarchical classification (optional; "
        "flat mode when absent or invalid).",
    )
    add_json_flag(classify_file_parser)
    for name, help_text in (
        ("classify-isjac", "Classify ISJAC mail as product bug, ops skip, or noise."),
        ("classify-ticket", "Classify a ticket's type, label, and priority."),
        ("classify-oncall", "Disposition an on-call alert."),
    ):
        add_json_flag(sub.add_parser(name, help=help_text))
    add_json_flag(
        sub.add_parser(
            "judge-turn",
            help="Judge an agent's final turn (JSON envelope on stdin): deferred, unproven, or fine.",
        )
    )
    add_json_flag(
        sub.add_parser(
            "judge-clarity",
            help="Judge whether a final message is clear enough to stop (JSON on stdin).",
        )
    )
    sub.add_parser("install-key", help="Copy TYPESAFE_API_KEY into the login keychain.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    getenv: Getenv = os.getenv,
    urlopen: Urlopen | None = None,
    read_keychain: ReadKeychain | None = None,
    skills: list[catalog.Skill] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = stdout if stdout is not None else sys.stdout
    incoming = stdin if stdin is not None else sys.stdin
    if args.command == "install-key":
        return install_key(getenv, out)
    if args.command == "pick-skill":
        try:
            context = json.loads(args.context) if args.context else None
        except (TypeError, ValueError):
            context = None
        if context is not None and not isinstance(context, dict):
            context = None
        result = pick_skill(
            args.prompt,
            getenv=getenv,
            urlopen=urlopen,
            read_keychain=read_keychain,
            skills=skills,
            in_flight=str(getattr(args, "in_flight", "") or ""),
            context=context,
        )
        emit_json(result.as_json(), out)
        return 0
    if args.command == "judge-turn":
        verdict = judge_turn(
            incoming.read(), getenv=getenv, urlopen=urlopen, read_keychain=read_keychain
        )
        emit_json(verdict.as_json(), out)
        return 0
    if args.command == "judge-clarity":
        verdict = judge_clarity(
            incoming.read(), getenv=getenv, urlopen=urlopen, read_keychain=read_keychain
        )
        emit_json(verdict.as_json(), out)
        return 0
    if args.command == "classify-findings":
        stamped = classify_findings(
            incoming.read(),
            getenv=getenv,
            urlopen=urlopen,
            read_keychain=read_keychain,
        )
        emit_json(stamped, out)
        return 0
    if args.command == "interrogate":
        try:
            result = interrogate(
                incoming.read(), getenv=getenv, urlopen=urlopen, read_keychain=read_keychain
            )
        except (OSError, TypeError, ValueError, systemone.JudgmentError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        emit_json(result, out)
        return 0
    if args.command == "classify-file":
        catalog_entries = classify_file.load_catalog(args.catalog)
        linear_projects = classify_file.load_linear_projects(args.linear_projects)
        for result in classify_files(
            args.paths,
            catalog_entries,
            linear_projects,
            getenv=getenv,
            urlopen=urlopen,
            read_keychain=read_keychain,
            taxonomy_path=args.taxonomy,
        ):
            emit_json(result.as_json(), out)
        return 0
    if args.command in GATES:
        result = judge_or_fallback(
            incoming.read(),
            GATES[args.command],
            getenv=getenv,
            urlopen=urlopen,
            read_keychain=read_keychain,
        )
        emit_json(result.as_json(), out)
        return 0
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
