"""Behavior tests for the typesafe CLI. Mock urllib; never hit the network."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType
from typing import Self
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent


def _load(name: str) -> ModuleType:
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


constants = _load("constants")
catalog = _load("catalog")
classify = _load("classify")
pick = _load("pick")
rerank = _load("rerank")
cli = _load("typesafe")

SECRET = "test-key-not-for-logs"
API_KEY_ENV = constants.API_KEY_ENV
# Names a test must never inherit from the real machine: `USER` unlocks the real keychain,
# and a real OpenRouter key would turn that hop on inside every mocked request chain.
MACHINE_CREDENTIAL_NAMES = frozenset({"USER", constants.OPENROUTER_API_KEY_ENV, constants.BASE_URL_ENV})
CHOICE_NONE = constants.CHOICE_NONE
SOURCE_FALLBACK = constants.SOURCE_FALLBACK
SOURCE_TYPESAFE = constants.SOURCE_TYPESAFE
ACTION_NO_CHANGE = constants.ACTION_NO_CHANGE
DESCRIPTION_CHARS = constants.DESCRIPTION_CHARS
ROSTER = [
    catalog.Skill(name="harness-efficiency", description="Audit coding-agent sessions."),
    catalog.Skill(name="tickets", description="File or update Linear tickets."),
]


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def getenv_with_key(name: str, default: str | None = None) -> str | None:
    if name == API_KEY_ENV:
        return SECRET
    return os.getenv(name, default) if name not in MACHINE_CREDENTIAL_NAMES else None


def getenv_without_key(name: str, default: str | None = None) -> str | None:
    if name == API_KEY_ENV:
        return None
    return os.getenv(name, default) if name not in MACHINE_CREDENTIAL_NAMES else None


def choice_answer(choice: str, confidence: float = 0.8, **weights: float) -> dict:
    probabilities = dict(weights) if weights else {choice: confidence}
    return {
        "type": "choice",
        "choice": choice,
        "confidence": confidence,
        "probabilities": probabilities,
    }


def noul_answer(value: float) -> dict:
    return {"type": "noul", "noul": value}


def score_answer(
    score: float,
    confidence: float = 0.9,
    probabilities: dict[str, float] | None = None,
) -> dict:
    if probabilities is None:
        nearest = min(max(int(score + 0.5), 0), 2)
        probabilities = {"0": 0.0, "1": 0.0, "2": 0.0}
        probabilities[str(nearest)] = 1.0
    return {
        "type": "score",
        "score": score,
        "confidence": confidence,
        "probabilities": probabilities,
        "legend": {
            "0": "same work",
            "1": "related",
            "2": "distinct outcome",
        },
    }


def wide_answers(
    skill: str, needs_skill: float = 0.9, confidence: float = 0.8, fit: float = 0.9
) -> dict:
    """Wide-rank and rerank answers in one map: mocks replay it for both requests."""
    return {
        "skill::0": choice_answer(skill, confidence, **{skill: confidence, "none": 0.09}),
        "gate::acts_on_user_system": noul_answer(needs_skill),
        "gate::would_follow_documented_procedure": noul_answer(needs_skill),
        "gate::prose_suffices": noul_answer(1.0 - needs_skill),
        "which": choice_answer(skill, confidence),
        f"fits::{skill}": noul_answer(fit),
    }


def decide(
    answers: dict,
    skills: list,
    usage: dict,
    in_flight: str = "",
    has_context: bool = False,
) -> pick.PickResult:
    wide = pick.read_wide(answers, skills, usage, in_flight, has_context)
    settled = pick.gate(wide, skills)
    if settled is not None:
        return settled
    choice, confidence, fits = rerank.decide(answers, wide.shortlist())
    return pick.settle(wide, skills, choice, confidence, fits)


def pick_payload(
    *,
    skill: str = "harness-efficiency",
    confidence: float = 0.91,
    needs_skill: float = 0.88,
    session_relation: float = 0.05,
    session_confidence: float = 0.9,
    session_probabilities: dict[str, float] | None = None,
    second_product: float | None = None,
) -> dict:
    answers: dict = wide_answers(skill, needs_skill, confidence)
    if second_product is not None:
        answers["second_product"] = noul_answer(second_product)
    else:
        probs = session_probabilities
        if probs is None and abs(session_relation - 0.05) < 1e-9:
            probs = {"0": 0.95, "1": 0.05, "2": 0.0}
        answers["session_relation"] = score_answer(
            session_relation,
            session_confidence,
            probs,
        )
    return {
        "model": "jev-1.13.0",
        "answers": answers,
        "usage": {"input_tokens": 120, "output_tokens": 8},
    }


def classify_payload(
    *,
    action: str = "join_zys_803",
    primitive: str = "subagent",
) -> dict:
    return {
        "model": "jev-1.13.0",
        "answers": {
            "action": choice_answer(action),
            "primitive": choice_answer(primitive),
        },
        "usage": {"input_tokens": 80, "output_tokens": 6},
    }


def http_error(code: int, body: bytes = b"overloaded") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.typesafe.ai/v1/systemone",
        code,
        "error",
        None,
        io.BytesIO(body),
    )


def run_pick(
    argv: list[str],
    *,
    getenv=getenv_with_key,
    urlopen=None,
    read_keychain=None,
    skills=None,
) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    keychain = read_keychain if read_keychain is not None else (lambda: None)
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(
            argv,
            getenv=getenv,
            urlopen=urlopen,
            read_keychain=keychain,
            skills=skills if skills is not None else ROSTER,
            stdout=stdout,
        )
    return code, stdout.getvalue(), stderr.getvalue()


def run_classify(
    payload: dict | str,
    *,
    getenv=getenv_with_key,
    urlopen=None,
    read_keychain=None,
) -> tuple[int, str, str]:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    stdout = io.StringIO()
    stderr = io.StringIO()
    keychain = read_keychain if read_keychain is not None else (lambda: None)
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = cli.main(
            ["classify-findings", "--json"],
            getenv=getenv,
            urlopen=urlopen,
            read_keychain=keychain,
            stdin=io.StringIO(raw),
            stdout=stdout,
        )
    return code, stdout.getvalue(), stderr.getvalue()


BAR_ROSTER = [
    catalog.Skill(name="bar", description="The craft bar for code quality."),
    catalog.Skill(name="review-bar", description="Review a change against the bar."),
    catalog.Skill(name="zq", description="Land a pull request."),
]


class CatalogTests(unittest.TestCase):
    def test_frontmatter_name_and_clipped_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill_dir = home / ".agents" / "skills" / "demo"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: demo\ndescription: " + ("x" * 200) + "\n---\n# Demo\n",
                encoding="utf-8",
            )
            skills = catalog.scan_skills(home)
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].name, "demo")
        self.assertEqual(len(skills[0].description), DESCRIPTION_CHARS)
        self.assertTrue(skills[0].path.endswith("/SKILL.md"))
        self.assertEqual(skills[0].load_paths, (skills[0].path,))

    def test_load_skill_sets_absolute_skill_md_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_md = Path(tmp) / "demo" / "SKILL.md"
            skill_md.parent.mkdir(parents=True)
            skill_md.write_text(
                "---\nname: demo\ndescription: Demo skill.\n---\n",
                encoding="utf-8",
            )
            skill = catalog.load_skill(skill_md)
        self.assertIsNotNone(skill)
        assert skill is not None
        self.assertTrue(skill.path.endswith("/SKILL.md"))
        self.assertEqual(Path(skill.path).resolve(), skill_md.resolve())
        self.assertEqual(skill.load_paths, (skill.path,))

    def test_folded_description_collapses_whitespace(self) -> None:
        text = "---\nname: folded\ndescription: >-\n  hello\n  world\n---\n"
        fields = catalog.parse_frontmatter(text)
        self.assertEqual(fields["name"], "folded")
        self.assertEqual(catalog.clip_description(fields["description"]), "hello world")

    def test_collapse_roster_hides_review_bar_when_bar_present(self) -> None:
        collapsed = catalog.collapse_roster(BAR_ROSTER)
        names = [skill.name for skill in collapsed]
        self.assertIn("bar", names)
        self.assertNotIn("review-bar", names)
        self.assertIn("zq", names)
        bar = next(skill for skill in collapsed if skill.name == "bar")
        self.assertEqual(bar.load, ("bar", "review-bar"))
        self.assertIn("review", bar.description.lower())
        self.assertIn("bar", bar.description.lower())

    def test_collapse_roster_load_paths_match_load_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {
                "bar": root / "bar" / "SKILL.md",
                "review-bar": root / "review-bar" / "SKILL.md",
                "zq": root / "zq" / "SKILL.md",
            }
            for name, path in paths.items():
                path.parent.mkdir(parents=True)
                path.write_text(
                    f"---\nname: {name}\ndescription: {name} skill.\n---\n",
                    encoding="utf-8",
                )
            skills = [catalog.load_skill(path) for path in paths.values()]
            self.assertTrue(all(skill is not None for skill in skills))
            collapsed = catalog.collapse_roster([skill for skill in skills if skill is not None])
            bar = next(skill for skill in collapsed if skill.name == "bar")
            self.assertEqual(bar.load, ("bar", "review-bar"))
            self.assertEqual(len(bar.load_paths), len(bar.load))
            self.assertEqual(
                bar.load_paths,
                (str(paths["bar"].resolve()), str(paths["review-bar"].resolve())),
            )
            for path in bar.load_paths:
                self.assertTrue(path.endswith("/SKILL.md"))
                self.assertTrue(Path(path).is_file())
            self.assertEqual(bar.path, str(paths["bar"].resolve()))

    def test_collapse_roster_keeps_review_bar_without_bar(self) -> None:
        skills = [catalog.Skill(name="review-bar", description="Review a change against the bar.")]
        collapsed = catalog.collapse_roster(skills)
        self.assertEqual([skill.name for skill in collapsed], ["review-bar"])

    def test_collapse_roster_hides_create_skill_without_loading_it(self) -> None:
        skills = [
            catalog.Skill(name="skill-creator", description="Author a new skill."),
            catalog.Skill(name="create-skill", description="Bundled skill creator."),
            catalog.Skill(
                name="skill-design-principles",
                description="Principles for skill design.",
            ),
        ]
        collapsed = catalog.collapse_roster(skills)
        names = [skill.name for skill in collapsed]
        self.assertEqual(names, ["skill-creator"])
        self.assertEqual(collapsed[0].load, ("skill-creator", "skill-design-principles"))

    def test_scan_skills_includes_available_skills_not_nested_two_levels(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            core = home / ".agents" / "skills" / "core"
            core.mkdir(parents=True)
            (core / "SKILL.md").write_text(
                "---\nname: core\ndescription: Auto-scan leftover.\n---\n",
                encoding="utf-8",
            )
            extra = home / ".agents" / "available-skills" / "extra"
            extra.mkdir(parents=True)
            (extra / "SKILL.md").write_text(
                "---\nname: extra\ndescription: Picker-only extra.\n---\n",
                encoding="utf-8",
            )
            nested = home / ".agents" / "available-skills" / "synced" / "uuid-folder"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text(
                "---\nname: nested-plugin\ndescription: Two levels deep.\n---\n",
                encoding="utf-8",
            )
            names = [skill.name for skill in catalog.scan_skills(home)]
        self.assertIn(".agents/skills", constants.SKILL_ROOTS)
        self.assertIn(".agents/available-skills", constants.SKILL_ROOTS)
        self.assertIn("core", names)
        self.assertIn("extra", names)
        self.assertNotIn("nested-plugin", names)


class PickSkillTests(unittest.TestCase):
    def test_live_shaped_success_selects_skill(self) -> None:
        payload = pick_payload()
        urlopen = mock.Mock(return_value=FakeHTTPResponse(payload))
        code, stdout, stderr = run_pick(
            ["pick-skill", "--prompt", "audit harness waste", "--json"],
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["choice"], "harness-efficiency")
        self.assertEqual(result["source"], SOURCE_TYPESAFE)
        self.assertEqual(result["needs_skill"], 0.88)
        self.assertEqual(result["confidence"], 0.91)
        self.assertEqual(result["usage"]["input_tokens"], 120)
        self.assertEqual(result["second_product"], 0.0)
        self.assertEqual(result["session_relation"], 0.05)
        self.assertFalse(result["split"])
        self.assertNotIn(SECRET, stdout)
        self.assertNotIn(SECRET, stderr)
        self.assertEqual(urlopen.call_count, 2)
        request = urlopen.call_args_list[0].args[0]
        self.assertIn("/v1/systemone", request.full_url)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 2.0)
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["questions"]["session_relation"]["type"], "score")
        self.assertEqual(body["state"]["in_flight"], constants.IN_FLIGHT_NONE)
        self.assertIn("prompt", body["state"])
        self.assertNotIn("skills", body["state"])

    def test_needs_skill_below_threshold_reports_none(self) -> None:
        below = round(constants.NEEDS_SKILL_THRESHOLD - 0.01, 2)
        payload = pick_payload(needs_skill=below)
        urlopen = mock.Mock(return_value=FakeHTTPResponse(payload))
        code, stdout, _stderr = run_pick(
            ["pick-skill", "--prompt", "thanks", "--json"],
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["choice"], CHOICE_NONE)
        self.assertEqual(result["source"], SOURCE_TYPESAFE)
        self.assertEqual(result["reason"], "needs_skill below threshold")
        self.assertAlmostEqual(result["needs_skill"], below)

    def test_timeout_falls_open(self) -> None:
        urlopen = mock.Mock(side_effect=TimeoutError("timed out"))
        code, stdout, stderr = run_pick(
            ["pick-skill", "--prompt", "thanks", "--json"],
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["choice"], CHOICE_NONE)
        self.assertEqual(result["source"], SOURCE_FALLBACK)
        self.assertEqual(result["reason"], "timeout")
        self.assertFalse(result["split"])
        self.assertEqual(result["second_product"], 0.0)
        self.assertEqual(result["session_relation"], 0.0)
        self.assertNotIn(SECRET, stdout + stderr)

    def test_timeout_local_pick_matches_tickets(self) -> None:
        urlopen = mock.Mock(side_effect=TimeoutError("timed out"))
        code, stdout, stderr = run_pick(
            [
                "pick-skill",
                "--prompt",
                "File a Linear ticket for explore dumps",
                "--json",
            ],
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["choice"], "tickets")
        self.assertEqual(result["source"], SOURCE_FALLBACK)
        self.assertEqual(result["reason"], "timeout")
        self.assertFalse(result["split"])
        self.assertEqual(result["second_product"], 0.0)
        self.assertEqual(result["session_relation"], 0.0)
        self.assertNotIn(SECRET, stdout + stderr)
        urlopen.assert_called()

    def test_http_529_falls_open(self) -> None:
        urlopen = mock.Mock(side_effect=http_error(529))
        code, stdout, _stderr = run_pick(
            ["pick-skill", "--prompt", "thanks", "--json"],
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["choice"], CHOICE_NONE)
        self.assertEqual(result["source"], SOURCE_FALLBACK)
        self.assertEqual(result["reason"], "http 529")

    def test_missing_key_falls_open_without_http(self) -> None:
        urlopen = mock.Mock()
        code, stdout, stderr = run_pick(
            ["pick-skill", "--prompt", "thanks", "--json"],
            getenv=getenv_without_key,
            urlopen=urlopen,
            read_keychain=lambda: None,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["choice"], CHOICE_NONE)
        self.assertEqual(result["source"], SOURCE_FALLBACK)
        self.assertEqual(result["reason"], "missing key")
        urlopen.assert_not_called()
        self.assertNotIn(SECRET, stdout + stderr)

    def test_missing_key_local_pick_matches_harness(self) -> None:
        urlopen = mock.Mock()
        code, stdout, stderr = run_pick(
            [
                "pick-skill",
                "--prompt",
                "audit coding-agent sessions for waste",
                "--json",
            ],
            getenv=getenv_without_key,
            urlopen=urlopen,
            read_keychain=lambda: None,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["choice"], "harness-efficiency")
        self.assertEqual(result["source"], SOURCE_FALLBACK)
        self.assertEqual(result["reason"], "missing key")
        urlopen.assert_not_called()
        self.assertNotIn(SECRET, stdout + stderr)

    def test_pick_skill_collapses_review_bar_from_choice_criteria(self) -> None:
        payload = pick_payload(skill="bar")
        urlopen = mock.Mock(return_value=FakeHTTPResponse(payload))
        code, stdout, _stderr = run_pick(
            ["pick-skill", "--prompt", "review against the bar", "--json"],
            urlopen=urlopen,
            skills=BAR_ROSTER,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["choice"], "bar")
        self.assertEqual(result["load"], ["bar", "review-bar"])
        body = json.loads(urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        criteria = body["questions"]["skill::0"]["criteria"]
        self.assertIn("bar", criteria)
        self.assertNotIn("review-bar", criteria)

    def test_empty_env_key_uses_keychain(self) -> None:
        def getenv(name: str, default: str | None = None) -> str | None:
            if name == API_KEY_ENV:
                return "  "
            return os.getenv(name, default)

        urlopen = mock.Mock(return_value=FakeHTTPResponse(pick_payload()))
        code, stdout, _stderr = run_pick(
            ["pick-skill", "--prompt", "audit", "--json"],
            getenv=getenv,
            urlopen=urlopen,
            read_keychain=lambda: SECRET,
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)["source"], SOURCE_TYPESAFE)
        self.assertEqual(urlopen.call_count, 2)


class ClassifyFindingsTests(unittest.TestCase):
    def test_live_shaped_success_stamps_join_and_primitive(self) -> None:
        finding = {
            "id": "subagent:explore-dump",
            "kind": "subagent",
            "session_count": 12,
            "proposed_primitive": "command",
        }
        urlopen = mock.Mock(return_value=FakeHTTPResponse(classify_payload()))
        code, stdout, stderr = run_classify(
            {
                "findings": [finding],
                "tickets": [{"id": "ZYS-803", "title": "Explore dumps"}],
            },
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        stamped = json.loads(stdout)
        self.assertEqual(len(stamped), 1)
        self.assertEqual(stamped[0]["typesafe_action"], "join_zys_803")
        self.assertEqual(stamped[0]["typesafe_primitive"], "subagent")
        self.assertEqual(stamped[0]["typesafe_source"], SOURCE_TYPESAFE)
        self.assertEqual(stamped[0]["proposed_primitive"], "command")
        body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertIn("join_zys_803", body["questions"]["action"]["criteria"])
        self.assertNotIn("join_ZYS-803", body["questions"]["action"]["criteria"])
        self.assertNotIn(SECRET, stdout + stderr)

    def test_low_session_count_skips_http_and_keeps_canned(self) -> None:
        finding = {
            "id": "repeated_shell:ls",
            "kind": "repeated_shell",
            "session_count": 3,
            "proposed_primitive": "command",
        }
        urlopen = mock.Mock()
        code, stdout, _stderr = run_classify(
            {"findings": [finding], "tickets": []},
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        stamped = json.loads(stdout)
        self.assertEqual(stamped[0]["typesafe_source"], SOURCE_FALLBACK)
        self.assertEqual(stamped[0]["typesafe_action"], ACTION_NO_CHANGE)
        self.assertEqual(stamped[0]["typesafe_primitive"], "command")
        urlopen.assert_not_called()

    def test_retry_kind_is_classified_below_session_floor(self) -> None:
        finding = {
            "id": "retry:tool",
            "kind": "retry",
            "session_count": 1,
            "proposed_primitive": "hook",
        }
        urlopen = mock.Mock(
            return_value=FakeHTTPResponse(classify_payload(action="file_new", primitive="hook"))
        )
        code, stdout, _stderr = run_classify(
            {"findings": [finding], "tickets": []},
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        stamped = json.loads(stdout)
        self.assertEqual(stamped[0]["typesafe_action"], "file_new")
        self.assertEqual(stamped[0]["typesafe_primitive"], "hook")
        self.assertEqual(stamped[0]["typesafe_source"], SOURCE_TYPESAFE)
        urlopen.assert_called_once()

    def test_http_529_leaves_canned_fields(self) -> None:
        finding = {
            "id": "long_session:grind",
            "kind": "long_session",
            "session_count": 4,
            "proposed_primitive": "subagent",
        }
        urlopen = mock.Mock(side_effect=http_error(529))
        code, stdout, _stderr = run_classify(
            {"findings": [finding], "tickets": []},
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        stamped = json.loads(stdout)
        self.assertEqual(stamped[0]["typesafe_source"], SOURCE_FALLBACK)
        self.assertEqual(stamped[0]["typesafe_action"], ACTION_NO_CHANGE)
        self.assertEqual(stamped[0]["typesafe_primitive"], "subagent")
        self.assertEqual(stamped[0]["proposed_primitive"], "subagent")

    def test_missing_key_falls_open(self) -> None:
        finding = {
            "id": "instruction_bloat:agents",
            "kind": "instruction_bloat",
            "session_count": 2,
            "proposed_primitive": "removal",
        }
        urlopen = mock.Mock()
        code, stdout, _stderr = run_classify(
            {"findings": [finding], "tickets": []},
            getenv=getenv_without_key,
            urlopen=urlopen,
            read_keychain=lambda: None,
        )
        self.assertEqual(code, 0)
        stamped = json.loads(stdout)
        self.assertEqual(stamped[0]["typesafe_source"], SOURCE_FALLBACK)
        urlopen.assert_not_called()

    def test_timeout_falls_open(self) -> None:
        finding = {
            "id": "model_routing:opus",
            "kind": "model_routing",
            "session_count": 8,
            "proposed_primitive": "none",
        }
        urlopen = mock.Mock(side_effect=TimeoutError("timed out"))
        code, stdout, _stderr = run_classify(
            {"findings": [finding], "tickets": []},
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout)[0]["typesafe_source"], SOURCE_FALLBACK)

    def test_bad_stdin_json_exits_zero_with_empty_list(self) -> None:
        code, stdout, _stderr = run_classify("not-json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout), [])

    def test_sanitize_ticket_id(self) -> None:
        self.assertEqual(classify.sanitize_ticket_id("ZYS-803"), "zys_803")
        self.assertEqual(classify.action_key("ZYS-803"), "join_zys_803")


class PolicyTests(unittest.TestCase):
    def test_pick_unknown_skill_becomes_none(self) -> None:
        answers = {
            **wide_answers("not-installed"),
        }
        result = decide(answers, ROSTER, {})
        self.assertEqual(result.choice, CHOICE_NONE)
        self.assertEqual(result.source, SOURCE_TYPESAFE)
        self.assertEqual(result.as_json()["load"], [])

    def test_build_request_criteria_omits_review_bar_when_bar_present(self) -> None:
        collapsed = catalog.collapse_roster(BAR_ROSTER)
        request = pick.build_request("review this against the bar", collapsed)
        criteria = request["questions"]["skill::0"]["criteria"]
        self.assertIn("bar", criteria)
        self.assertNotIn("review-bar", criteria)
        self.assertIn("review", criteria["bar"].lower())

    def test_decide_json_load_includes_folded_files(self) -> None:
        collapsed = catalog.collapse_roster(BAR_ROSTER)
        answers = {
            **wide_answers("bar"),
        }
        result = decide(answers, collapsed, {})
        payload = result.as_json()
        self.assertEqual(payload["choice"], "bar")
        self.assertEqual(payload["load"], ["bar", "review-bar"])
        self.assertEqual(payload["paths"], [])

    def test_decide_json_paths_match_load_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bar_path = root / "bar" / "SKILL.md"
            review_path = root / "review-bar" / "SKILL.md"
            for path, name, desc in (
                (bar_path, "bar", "The craft bar for code quality."),
                (review_path, "review-bar", "Review a change against the bar."),
            ):
                path.parent.mkdir(parents=True)
                path.write_text(
                    f"---\nname: {name}\ndescription: {desc}\n---\n",
                    encoding="utf-8",
                )
            skills = [
                skill
                for skill in (
                    catalog.load_skill(bar_path),
                    catalog.load_skill(review_path),
                )
                if skill is not None
            ]
            collapsed = catalog.collapse_roster(skills)
            answers = {
                **wide_answers("bar"),
            }
            payload = decide(answers, collapsed, {}).as_json()
            self.assertEqual(payload["load"], ["bar", "review-bar"])
            self.assertEqual(len(payload["paths"]), len(payload["load"]))
            self.assertEqual(
                payload["paths"],
                [str(bar_path.resolve()), str(review_path.resolve())],
            )
            for path in payload["paths"]:
                self.assertTrue(path.endswith("/SKILL.md"))
                self.assertTrue(Path(path).is_file())

    def test_local_pick_json_load_includes_folded_files(self) -> None:
        collapsed = catalog.collapse_roster(BAR_ROSTER)
        result = pick.local_pick("review this against the bar", collapsed)
        payload = result.as_json()
        self.assertEqual(payload["choice"], "bar")
        self.assertEqual(payload["load"], ["bar", "review-bar"])
        self.assertEqual(payload["paths"], [])

    def test_local_pick_ungrouped_load_is_choice(self) -> None:
        result = pick.local_pick("File a Linear ticket for explore dumps", ROSTER)
        self.assertEqual(result.choice, "tickets")
        self.assertEqual(result.as_json()["load"], ["tickets"])
        self.assertEqual(result.as_json()["paths"], [])

    def test_none_json_load_is_empty(self) -> None:
        payload = pick.fallback().as_json()
        self.assertEqual(payload["load"], [])
        self.assertEqual(payload["paths"], [])

    def test_high_session_relation_with_in_flight_splits(self) -> None:
        payload = pick_payload(
            skill="tickets",
            session_relation=1.94,
            session_confidence=0.92,
            session_probabilities={"0": 0.0, "1": 0.06, "2": 0.94},
        )
        urlopen = mock.Mock(return_value=FakeHTTPResponse(payload))
        code, stdout, _stderr = run_pick(
            [
                "pick-skill",
                "--prompt",
                "also land zq live while evo workers run",
                "--in-flight",
                "Sync Mac licks to iPad",
                "--json",
            ],
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["choice"], "tickets")
        self.assertEqual(result["source"], SOURCE_TYPESAFE)
        self.assertTrue(result["split"])
        self.assertEqual(result["session_relation"], 1.94)
        self.assertEqual(result["second_product"], 0.94)
        body = json.loads(urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        self.assertEqual(body["state"]["in_flight"], "Sync Mac licks to iPad")
        self.assertEqual(body["questions"]["session_relation"]["type"], "score")

    def test_high_session_relation_without_in_flight_does_not_split(self) -> None:
        payload = pick_payload(
            skill="tickets",
            session_relation=1.94,
            session_confidence=0.92,
            session_probabilities={"0": 0.0, "1": 0.06, "2": 0.94},
        )
        urlopen = mock.Mock(return_value=FakeHTTPResponse(payload))
        code, stdout, _stderr = run_pick(
            [
                "pick-skill",
                "--prompt",
                "also land zq live while evo workers run",
                "--json",
            ],
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertFalse(result["split"])
        self.assertEqual(result["session_relation"], 1.94)

    def test_high_new_task_probability_splits_with_durable_context(self) -> None:
        answers = {
            **wide_answers("tickets"),
            "session_relation": {
                "type": "score",
                "score": 1.54,
                "probabilities": {"0": 0.1, "1": 0.14, "2": 0.76},
            },
        }
        result = decide(
            answers,
            ROSTER,
            {},
            has_context=True,
        )
        self.assertTrue(result.split)
        self.assertEqual(result.second_product, 0.76)

    def test_low_session_relation_does_not_split(self) -> None:
        payload = pick_payload(
            session_relation=0.1,
            session_confidence=0.9,
            session_probabilities={"0": 0.9, "1": 0.1, "2": 0.0},
        )
        urlopen = mock.Mock(return_value=FakeHTTPResponse(payload))
        code, stdout, _stderr = run_pick(
            [
                "pick-skill",
                "--prompt",
                "audit harness waste",
                "--in-flight",
                "harness efficiency audit",
                "--json",
            ],
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["choice"], "harness-efficiency")
        self.assertFalse(result["split"])
        self.assertEqual(result["session_relation"], 0.1)
        self.assertEqual(result["second_product"], 0.0)

    def test_high_session_relation_splits_even_with_low_score_confidence(self) -> None:
        payload = pick_payload(
            session_relation=1.9,
            session_confidence=0.2,
            session_probabilities={"0": 0.05, "1": 0.0, "2": 0.95},
        )
        urlopen = mock.Mock(return_value=FakeHTTPResponse(payload))
        code, stdout, _stderr = run_pick(
            [
                "pick-skill",
                "--prompt",
                "person menu gravatar",
                "--in-flight",
                "Sync Mac licks to iPad",
                "--json",
            ],
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertTrue(result["split"])
        self.assertEqual(result["session_relation"], 1.9)
        self.assertEqual(result["second_product"], 0.95)

    def test_missing_score_confidence_still_splits_on_high_p2(self) -> None:
        answers = {
            **wide_answers("tickets"),
            "session_relation": {
                "type": "score",
                "score": 1.9,
                "probabilities": {"0": 0.05, "1": 0.0, "2": 0.95},
            },
        }
        result = decide(
            answers,
            ROSTER,
            {},
            in_flight="Sync Mac licks to iPad",
        )
        self.assertTrue(result.split)
        self.assertEqual(result.second_product, 0.95)
        self.assertEqual(result.session_relation, 1.9)

    def test_top_level_nearest_with_low_p2_does_not_split(self) -> None:
        payload = pick_payload(
            session_relation=1.6,
            session_confidence=0.9,
            session_probabilities={"0": 0.1, "1": 0.5, "2": 0.4},
        )
        urlopen = mock.Mock(return_value=FakeHTTPResponse(payload))
        code, stdout, _stderr = run_pick(
            [
                "pick-skill",
                "--prompt",
                "person menu gravatar",
                "--in-flight",
                "Sync Mac licks to iPad",
                "--json",
            ],
            urlopen=urlopen,
        )
        self.assertEqual(code, 0)
        result = json.loads(stdout)
        self.assertFalse(result["split"])
        self.assertEqual(result["session_relation"], 1.6)
        self.assertEqual(result["second_product"], 0.4)

    def test_missing_score_accepts_legacy_noul(self) -> None:
        answers = {
            **wide_answers("tickets"),
            "second_product": noul_answer(0.97),
        }
        with_flight = decide(
            answers,
            ROSTER,
            {},
            in_flight="evo workers in flight",
        )
        self.assertEqual(with_flight.choice, "tickets")
        self.assertTrue(with_flight.split)
        self.assertEqual(with_flight.second_product, 0.97)
        self.assertEqual(with_flight.session_relation, 0.0)
        without_flight = decide(answers, ROSTER, {})
        self.assertFalse(without_flight.split)

    def test_missing_session_relation_does_not_split(self) -> None:
        answers = {
            **wide_answers("tickets"),
        }
        result = decide(answers, ROSTER, {}, in_flight="open work")
        self.assertEqual(result.choice, "tickets")
        self.assertFalse(result.split)
        self.assertEqual(result.second_product, 0.0)
        self.assertEqual(result.session_relation, 0.0)

    def test_malformed_session_relation_does_not_raise(self) -> None:
        answers = {
            **wide_answers("tickets"),
            "session_relation": {"type": "score", "score": "nope"},
        }
        result = decide(answers, ROSTER, {}, in_flight="open work")
        self.assertEqual(result.choice, "tickets")
        self.assertFalse(result.split)
        self.assertEqual(result.session_relation, 0.0)

    def test_malformed_legacy_second_product_does_not_raise(self) -> None:
        answers = {
            **wide_answers("tickets"),
            "second_product": {"type": "noul", "noul": "nope"},
        }
        result = decide(answers, ROSTER, {}, in_flight="open work")
        self.assertEqual(result.choice, "tickets")
        self.assertFalse(result.split)
        self.assertEqual(result.second_product, 0.0)

    def test_fallback_and_local_pick_do_not_split(self) -> None:
        self.assertFalse(pick.fallback().split)
        self.assertEqual(pick.fallback().second_product, 0.0)
        self.assertEqual(pick.fallback().session_relation, 0.0)
        local = pick.local_pick("File a Linear ticket for explore dumps", ROSTER)
        self.assertEqual(local.choice, "tickets")
        self.assertFalse(local.split)
        self.assertEqual(local.second_product, 0.0)
        self.assertEqual(local.session_relation, 0.0)
        self.assertFalse(local.as_json()["split"])
        self.assertEqual(local.as_json()["session_relation"], 0.0)


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    tests.addTests(loader.loadTestsFromModule(_load("test_classify_gates")))
    return tests


if __name__ == "__main__":
    unittest.main()


class BaseUrlFallbackTests(unittest.TestCase):
    def ask(self, urlopen: mock.Mock, env: dict[str, str] | None = None) -> dict:
        import systemone

        return systemone.ask(
            {"model": "jev-latest", "state": {}, "questions": {}},
            SECRET,
            getenv=(env or {}).get,
            urlopen=urlopen,
        )

    def test_hosted_answers_first(self) -> None:
        urlopen = mock.Mock(return_value=FakeHTTPResponse({"answers": {}}))
        self.ask(urlopen)
        self.assertEqual(urlopen.call_count, 1)
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.startswith(constants.HOSTED_BASE_URL))
        self.assertEqual(json.loads(request.data)["model"], "jev-latest")

    def test_falls_through_to_local_on_429(self) -> None:
        urlopen = mock.Mock(side_effect=[http_error(429), FakeHTTPResponse({"answers": {}})])
        self.ask(urlopen)
        urls = [c.args[0].full_url for c in urlopen.call_args_list]
        self.assertEqual(urls[1], constants.LOCAL_BASE_URL + constants.SYSTEMONE_PATH)
        self.assertEqual(json.loads(urlopen.call_args.args[0].data)["model"], "jev-1.13.0:latest")

    def test_env_base_url_skips_hosted(self) -> None:
        urlopen = mock.Mock(return_value=FakeHTTPResponse({"answers": {}}))
        self.ask(urlopen, {"TYPESAFE_BASE_URL": constants.LOCAL_BASE_URL})
        self.assertEqual(urlopen.call_count, 1)
        self.assertTrue(urlopen.call_args.args[0].full_url.startswith(constants.LOCAL_BASE_URL))

    def test_adapt_shapes_payload_per_base_url(self) -> None:
        import systemone

        urlopen = mock.Mock(side_effect=[http_error(429), FakeHTTPResponse({"answers": {}})])
        systemone.ask(
            {"model": "jev-latest", "state": {}, "questions": {}},
            SECRET,
            getenv={}.get,
            urlopen=urlopen,
            adapt=lambda base, payload: {**payload, "state": {"base": base}},
        )
        bases = [json.loads(c.args[0].data)["state"]["base"] for c in urlopen.call_args_list]
        self.assertEqual(bases, [constants.HOSTED_BASE_URL, constants.LOCAL_BASE_URL])

    def test_openrouter_answers_first_with_its_own_key_and_model(self) -> None:
        urlopen = mock.Mock(return_value=FakeHTTPResponse({"answers": {}}))
        self.ask(urlopen, {"OPENROUTER_API_KEY": "or-key"})
        self.assertEqual(urlopen.call_count, 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/systemone")
        self.assertEqual(request.get_header("Authorization"), "Bearer or-key")
        self.assertEqual(json.loads(request.data)["model"], "typesafe/jev-1.14")

    def test_openrouter_failure_falls_through_to_hosted_with_the_typesafe_key(self) -> None:
        urlopen = mock.Mock(side_effect=[http_error(402), FakeHTTPResponse({"answers": {}})])
        self.ask(urlopen, {"OPENROUTER_API_KEY": "or-key"})
        second = urlopen.call_args.args[0]
        self.assertTrue(second.full_url.startswith(constants.HOSTED_BASE_URL))
        self.assertEqual(second.get_header("Authorization"), f"Bearer {SECRET}")
        self.assertEqual(json.loads(second.data)["model"], "jev-latest")

    def test_without_an_openrouter_key_the_hop_is_skipped_not_failed(self) -> None:
        urlopen = mock.Mock(side_effect=[http_error(429), http_error(503)])
        import systemone

        with self.assertRaises(systemone.JudgmentError) as ctx:
            self.ask(urlopen)
        self.assertEqual(ctx.exception.hops, "api.typesafe.ai http 429 > localhost http 503")

    def test_last_failure_propagates(self) -> None:
        import systemone

        urlopen = mock.Mock(side_effect=[http_error(429), http_error(503)])
        with self.assertRaises(systemone.JudgmentError) as ctx:
            self.ask(urlopen)
        self.assertEqual(ctx.exception.reason, "http 503")

    def test_error_records_every_hop(self) -> None:
        import systemone

        urlopen = mock.Mock(side_effect=[http_error(429), http_error(503)])
        with self.assertRaises(systemone.JudgmentError) as ctx:
            self.ask(urlopen)
        self.assertEqual(ctx.exception.hops, "api.typesafe.ai http 429 > localhost http 503")

    def test_single_hop_failure_has_no_hop_chain(self) -> None:
        import systemone

        urlopen = mock.Mock(side_effect=[http_error(503)])
        with self.assertRaises(systemone.JudgmentError) as ctx:
            self.ask(urlopen, {"TYPESAFE_BASE_URL": constants.LOCAL_BASE_URL})
        self.assertEqual((ctx.exception.reason, ctx.exception.hops), ("http 503", ""))


class TwoRequestPickTests(unittest.TestCase):
    def pick(self, urlopen: mock.Mock, read_text=lambda _path: None) -> dict:
        result = cli.pick_skill(
            "audit harness waste",
            getenv=getenv_with_key,
            urlopen=urlopen,
            read_keychain=lambda: None,
            skills=ROSTER,
            read_text=read_text,
        )
        return result.as_json()

    def test_gate_below_threshold_skips_rerank(self) -> None:
        urlopen = mock.Mock(return_value=FakeHTTPResponse(pick_payload(needs_skill=0.1)))
        result = self.pick(urlopen)
        self.assertEqual(result["choice"], CHOICE_NONE)
        self.assertEqual(urlopen.call_count, 1)

    def test_low_fits_drop_the_shortlist(self) -> None:
        answers = wide_answers("harness-efficiency", fit=0.1)
        urlopen = mock.Mock(return_value=FakeHTTPResponse({"answers": answers}))
        result = self.pick(urlopen)
        self.assertEqual(result["choice"], CHOICE_NONE)
        self.assertEqual(result["reason"], constants.REASON_NO_FIT)
        self.assertEqual(result["shortlist"], ["harness-efficiency"])
        self.assertEqual(result["fits"], {"harness-efficiency": 0.1})

    def test_failed_rerank_suggests_nothing(self) -> None:
        wide = FakeHTTPResponse(pick_payload())
        urlopen = mock.Mock(side_effect=[wide, http_error(503), http_error(503)])
        result = self.pick(urlopen)
        self.assertEqual(result["choice"], CHOICE_NONE)
        self.assertEqual(result["source"], SOURCE_TYPESAFE)
        self.assertEqual(result["reason"], f"{constants.REASON_RERANK_FAILED}: http 503")

    def test_rerank_reads_skill_body_excerpt(self) -> None:
        urlopen = mock.Mock(return_value=FakeHTTPResponse(pick_payload()))
        text = "---\nname: harness-efficiency\ndescription: Full description.\n---\n# Body\nSteps."
        self.pick(urlopen, read_text=lambda _path: text)
        body = json.loads(urlopen.call_args_list[1].args[0].data)
        criteria = body["questions"]["which"]["criteria"]
        self.assertEqual(criteria["harness-efficiency"], "Full description. — # Body\nSteps.")
        self.assertIn("fits::harness-efficiency", body["questions"])

    def test_hosted_ranks_whole_roster_in_one_choice(self) -> None:
        roster = [catalog.Skill(name=f"s{index}", description="d") for index in range(111)]
        request = pick.for_base(pick.build_request("x", roster), roster, constants.HOSTED_BASE_URL)
        skill_questions = [k for k in request["questions"] if k.startswith(pick.SKILL_PREFIX)]
        self.assertEqual(skill_questions, [f"{pick.SKILL_PREFIX}0"])
        self.assertEqual(len(request["questions"][skill_questions[0]]["criteria"]), 112)

    def test_winner_needs_its_own_fit(self) -> None:
        reply = {
            "which": choice_answer("a"),
            "fits::a": noul_answer(0.04),
            "fits::b": noul_answer(0.73),
        }
        choice, _confidence, _fits = rerank.decide(reply, ["a", "b"])
        self.assertEqual(choice, CHOICE_NONE)

    def test_roster_chunks_fit_local_choice_limit(self) -> None:
        roster = [catalog.Skill(name=f"s{index}", description="d") for index in range(111)]
        request = pick.for_base(pick.build_request("x", roster), roster, constants.LOCAL_BASE_URL)
        questions = {
            k: v for k, v in request["questions"].items() if k.startswith(pick.SKILL_PREFIX)
        }
        names = [n for q in questions.values() for n in q["criteria"] if n != CHOICE_NONE]
        self.assertEqual(sorted(names), sorted(skill.name for skill in roster))
        for question in questions.values():
            self.assertLessEqual(len(question["criteria"]), constants.PICK_CHOICE_MAX_OPTIONS)
            self.assertGreaterEqual(len(question["criteria"]), 2)

    def test_session_relation_criteria_are_strings(self) -> None:
        criteria = pick.build_session_relation_question()["criteria"]
        self.assertTrue(all(isinstance(item, str) for item in criteria))

    def test_skill_body_strips_frontmatter(self) -> None:
        self.assertEqual(catalog.skill_body("---\nname: x\n---\n\nBody"), "Body")
        self.assertEqual(catalog.skill_body("No frontmatter"), "No frontmatter")
