"""Behavior tests for classify-file: prefilter, observation, shortlist scoring, and
the single-batched TypeSafe gate (typesafe-skills rules 4/8, examples 13/14/19)."""

from __future__ import annotations

import importlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Self
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

constants = importlib.import_module("constants")
classify_file = importlib.import_module("classify_file")
cli = importlib.import_module("typesafe")

SECRET = "test-key-not-for-logs"
API_KEY_ENV = constants.API_KEY_ENV


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
    return os.getenv(name, default)


def getenv_without_key(name: str, default: str | None = None) -> str | None:
    if name == API_KEY_ENV:
        return None
    return os.getenv(name, default)


def choice_answer(
    choice: str, confidence: float = 0.8, probabilities: dict[str, float] | None = None
) -> dict:
    answer: dict = {"type": "choice", "choice": choice, "confidence": confidence}
    if probabilities is not None:
        answer["probabilities"] = probabilities
    return answer


def noul_answer(value: float) -> dict:
    return {"type": "noul", "noul": value}


def flag_answers(
    *,
    backup: float = 0.0,
    issue_list: float = 0.0,
    evidence: float = 0.0,
    private: float = 0.0,
    regenerable: float = 0.0,
    loss_record: float = 0.0,
) -> dict:
    """The 6 disposition flag Nouls (design section 2.2/11) that replace the old
    `disposition` Choice in flat mode. Every flag defaults to 0.0 (not raised) so a
    test only has to name the flags it cares about."""
    return {
        constants.FILE_FLAG_BACKUP: noul_answer(backup),
        constants.FILE_FLAG_ISSUE_LIST: noul_answer(issue_list),
        constants.FILE_FLAG_EVIDENCE: noul_answer(evidence),
        constants.FILE_FLAG_PRIVATE: noul_answer(private),
        constants.FILE_FLAG_REGENERABLE: noul_answer(regenerable),
        constants.FILE_FLAG_LOSS_RECORD: noul_answer(loss_record),
    }


def catalog_entry(full_name: str, keywords: list[str], local_path: str = "") -> dict:
    return {
        "full_name": full_name,
        "keywords": keywords,
        "description_proposed": "",
        "local_path": local_path or None,
    }


# A representative slice of the real 165-repo catalog: the named live-bug repos plus
# distractors that share generic keywords, to prove candidate narrowing and rarity
# weighting behave like the real corpus (not just a two-repo toy fixture).
SAMPLE_CATALOG = [
    catalog_entry(
        "zachbornheimer/agentmux",
        ["agentmux", "orchestrator", "tmux", "go"],
        local_path="/Users/zbornheimer/Developer/Personal/agentmux",
    ),
    catalog_entry("zachbornheimer/zq", ["zq", "worktree", "lefthook", "mise", "go"]),
    catalog_entry(
        "zachbornheimer/evident-output", ["evo", "evident-output", "cli", "progress", "go"]
    ),
    catalog_entry(
        "ZAB-AI-LLC/obsidian-backup",
        ["obsidian-backup", "backup", "encryption", "deduplication", "go", "sync"],
    ),
    catalog_entry(
        "ZAB-AI-LLC/obsidian-backup-macos",
        ["obsidian-backup", "macos", "swiftui", "menu-bar"],
    ),
    catalog_entry("ZAB-AI-LLC/obsidian-vault", ["obsidian-backup", "obsidian-vault", "supabase"]),
    catalog_entry("zysys/flight", ["flight", "github-pr", "automerge", "railway"]),
    catalog_entry("zysys/flight-live-test", ["flight", "live-test", "integration-test", "proof"]),
    catalog_entry(
        "Software-Automation-Holdings-LLC/rapidsign",
        ["rapidsign", "isaapi", "document signing", "e-signature", "lambda"],
    ),
    catalog_entry(
        "Software-Automation-Holdings-LLC/rapidsign-sdk-go",
        ["rapidsign", "sdk", "go", "generated", "mirror"],
    ),
    catalog_entry(
        "Software-Automation-Holdings-LLC/sdk", ["sdk", "go sdk", "unified sdk", "rapidsign"]
    ),
    catalog_entry("zachbornheimer/homelab", ["homelab", "nas", "docker", "compose"]),
    catalog_entry("zachbornheimer/nas-recovery", ["nas-recovery", "synology", "btrfs"]),
    # noise: many unrelated repos sharing common words like "go"/"cli"/"sdk" that must
    # not dilute a strong single-repo signal for e.g. "agentmux" or "zq".
    *[catalog_entry(f"org/generic-tool-{i}", ["go", "cli", "sdk", "tooling"]) for i in range(6)],
]
SAMPLE_LINEAR_PROJECTS = [
    {"name": "AgentMux"},
    {"name": "ZQ"},
    {"name": "Evident Output"},
    {"name": "Flight"},
    {"name": "Homelab"},
    {"name": "ISJAC"},
]


def observation_for(filename: str, excerpt: str = "") -> dict:
    return {
        "path": f"/tmp/{filename}",
        "filename": filename,
        "extension": Path(filename).suffix.lower(),
        "size": 10,
        "mtime": "2026-01-01T00:00:00+00:00",
        "is_dir": False,
        "excerpt": excerpt,
        "entries": [],
    }


def shortlist_names(
    observation: dict, catalog_entries: list[dict], linear_projects: list[dict]
) -> list[str]:
    return [
        name
        for name, _description in classify_file._shortlist(
            observation, catalog_entries, linear_projects
        )
    ]


def answers_for(
    observation: dict,
    catalog_entries: list[dict],
    linear_projects: list[dict],
    *,
    matches: dict[str, float] | None = None,
    kind: str = "spec",
    kind_confidence: float = 0.9,
    backup: float = 0.0,
    issue_list: float = 0.0,
    evidence: float = 0.0,
    private: float = 0.0,
    regenerable: float = 0.0,
    loss_record: float = 0.0,
) -> dict:
    """Build a decide()-ready answers dict: per-candidate Nouls (keyed by the same
    shortlist order build_request/decide compute internally) plus kind and the 6
    disposition flag Nouls decide() now reads instead of a disposition Choice."""
    matches = matches or {}
    shortlist = classify_file._shortlist(observation, catalog_entries, linear_projects)
    answers_by_id: dict = {}
    for index, (name, _description) in enumerate(shortlist):
        if name in matches:
            answers_by_id[f"match_{index}"] = noul_answer(matches[name])
    answers_by_id["kind"] = choice_answer(kind, kind_confidence)
    answers_by_id.update(
        flag_answers(
            backup=backup,
            issue_list=issue_list,
            evidence=evidence,
            private=private,
            regenerable=regenerable,
            loss_record=loss_record,
        )
    )
    return answers_by_id


class ProjectCandidateScoringTests(unittest.TestCase):
    """Regression for the live 165-repo run: the model was offered ~190 undifferentiated
    labels and most files fell below the confidence floor. These prove deterministic
    candidate narrowing (typesafe-skills examples 14/19) fixes it structurally."""

    def test_agentmux_filename_is_a_strong_unique_match(self) -> None:
        observation = observation_for("agentmux-ui-research-pass.md")
        self.assertEqual(
            classify_file.strong_project_match(observation, SAMPLE_CATALOG),
            "zachbornheimer/agentmux",
        )

    def test_zq_filename_is_a_strong_unique_match(self) -> None:
        observation = observation_for("zq-live-notes.md")
        self.assertEqual(
            classify_file.strong_project_match(observation, SAMPLE_CATALOG), "zachbornheimer/zq"
        )

    def test_evo_filename_is_a_strong_unique_match(self) -> None:
        observation = observation_for("evo-dialect-axes-review.md")
        self.assertEqual(
            classify_file.strong_project_match(observation, SAMPLE_CATALOG),
            "zachbornheimer/evident-output",
        )

    def test_obsidian_alone_is_too_ambiguous_for_a_strong_match(self) -> None:
        # "obsidian" alone matches 3 repos (backup, backup-macos, vault) — must not
        # blind-guess; falls through to the scored candidate list instead.
        observation = observation_for("obsidian-live-proof-20260713-101402.txt")
        self.assertIsNone(classify_file.strong_project_match(observation, SAMPLE_CATALOG))

    def test_no_catalog_signal_has_no_strong_match(self) -> None:
        observation = observation_for("ZBbio.md")
        self.assertIsNone(classify_file.strong_project_match(observation, SAMPLE_CATALOG))

    def test_obsidian_ranks_above_a_generic_shared_token_distractor(self) -> None:
        # Regression: obsidian-live-proof-*.txt was wrongly routed to
        # zysys/flight-live-test (shares only the generic word "live") instead of an
        # obsidian-backup repo (shares the rare, distinctive word "obsidian").
        observation = observation_for("obsidian-live-proof-20260713-101402.txt")
        candidates = shortlist_names(observation, SAMPLE_CATALOG, [])
        obsidian_repos = [name for name in candidates if "obsidian" in name.lower()]
        self.assertTrue(obsidian_repos, "expected at least one obsidian-* candidate offered")
        self.assertNotIn("zysys/flight-live-test", candidates)

    def test_candidate_set_is_bounded_not_the_whole_catalog(self) -> None:
        observation = observation_for("random-desktop-notes.md")
        candidates = shortlist_names(observation, SAMPLE_CATALOG, SAMPLE_LINEAR_PROJECTS)
        # personal buckets + a small bounded top-K, never every catalog repo.
        self.assertLess(len(candidates), len(SAMPLE_CATALOG) + len(SAMPLE_LINEAR_PROJECTS))

    def test_same_named_linear_project_is_shadowed_by_matching_repo(self) -> None:
        observation = observation_for("agentmux-ui-research-pass.md")
        candidates = shortlist_names(observation, SAMPLE_CATALOG, SAMPLE_LINEAR_PROJECTS)
        self.assertIn("zachbornheimer/agentmux", candidates)
        self.assertNotIn("linear:AgentMux", candidates)

    def test_shortlist_always_includes_personal_buckets(self) -> None:
        observation = observation_for("random-desktop-notes.md")
        candidates = set(shortlist_names(observation, [], []))
        self.assertTrue(candidates.issuperset(constants.FILE_PERSONAL_BUCKET_CRITERIA))


class ObserveTests(unittest.TestCase):
    def test_text_file_reads_bounded_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("hello world", encoding="utf-8")
            observation = classify_file.observe(path)
            self.assertEqual(observation["filename"], "notes.md")
            self.assertEqual(observation["extension"], ".md")
            self.assertEqual(observation["excerpt"], "hello world")
            self.assertFalse(observation["is_dir"])

    def test_text_content_cap_is_well_beyond_a_thin_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "long.md"
            path.write_text("x" * 10_000, encoding="utf-8")
            observation = classify_file.observe(path)
            self.assertGreater(len(observation["excerpt"]), 8000)

    def test_image_extension_skips_content_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "photo.png"
            path.write_bytes(b"\x89PNG\r\n")
            observation = classify_file.observe(path)
            self.assertEqual(observation["excerpt"], "")

    def test_directory_lists_bounded_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            (root / "a.txt").write_text("a", encoding="utf-8")
            (root / "b.txt").write_text("b", encoding="utf-8")
            observation = classify_file.observe(root)
            self.assertTrue(observation["is_dir"])
            self.assertEqual(observation["entries"], ["a.txt", "b.txt"])

    def test_directory_samples_text_of_files_inside(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "notes.scriv"
            root.mkdir()
            (root / "chapter-one.txt").write_text("the beginning", encoding="utf-8")
            observation = classify_file.observe(root)
            self.assertIn("chapter-one.txt", observation["excerpt"])
            self.assertIn("the beginning", observation["excerpt"])

    def test_missing_path_raises_file_not_found(self) -> None:
        with self.assertRaises(FileNotFoundError):
            classify_file.observe(Path("/nonexistent/does-not-exist.md"))

    def test_docx_like_file_uses_textutil_facade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.docx"
            path.write_bytes(b"not-real-docx-bytes")
            observation = classify_file.observe(path, run_textutil=lambda p: "extracted docx text")
            self.assertEqual(observation["excerpt"], "extracted docx text")

    def test_textutil_failure_falls_open_to_empty_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.rtf"
            path.write_bytes(b"not-real-rtf-bytes")
            observation = classify_file.observe(path, run_textutil=lambda p: None)
            self.assertEqual(observation["excerpt"], "")

    def test_pdf_file_uses_pdftotext_facade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.pdf"
            path.write_bytes(b"%PDF-1.4 not real")
            observation = classify_file.observe(path, run_pdftotext=lambda p: "extracted pdf text")
            self.assertEqual(observation["excerpt"], "extracted pdf text")

    def test_html_file_strips_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guide.html"
            path.write_text(
                "<html><body><script>bad()</script><h1>ISJAC Brand</h1></body></html>",
                encoding="utf-8",
            )
            observation = classify_file.observe(path)
            self.assertIn("ISJAC Brand", observation["excerpt"])
            self.assertNotIn("<h1>", observation["excerpt"])
            self.assertNotIn("bad()", observation["excerpt"])

    def test_zip_file_reads_first_text_member(self) -> None:
        import zipfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("readme.md", "packaged notes")
            observation = classify_file.observe(path)
            self.assertIn("packaged notes", observation["excerpt"])


class PrefilterTests(unittest.TestCase):
    def _observation(self, filename: str) -> dict:
        return {
            "path": f"/tmp/{filename}",
            "filename": filename,
            "extension": Path(filename).suffix.lower(),
            "size": 10,
            "mtime": "2026-01-01T00:00:00+00:00",
            "is_dir": False,
            "excerpt": "",
            "entries": [],
        }

    def test_backup_suffix_is_trash_candidate(self) -> None:
        result = classify_file.prefilter(self._observation("notes.bkup"))
        assert result is not None
        self.assertEqual(result.kind, "backup")
        self.assertEqual(result.disposition, "trash-candidate")

    def test_copy_suffix_is_trash_candidate(self) -> None:
        result = classify_file.prefilter(self._observation("report copy.json"))
        assert result is not None
        self.assertEqual(result.disposition, "trash-candidate")

    def test_old_suffix_is_trash_candidate(self) -> None:
        result = classify_file.prefilter(self._observation("plan-old.md"))
        assert result is not None
        self.assertEqual(result.disposition, "trash-candidate")

    def test_screenshot_filename_is_screenshot_kind(self) -> None:
        result = classify_file.prefilter(
            self._observation("Screenshot 2026-01-01 at 9.00.00 AM.png")
        )
        assert result is not None
        self.assertEqual(result.kind, "screenshot")

    def test_video_extension_is_media(self) -> None:
        result = classify_file.prefilter(self._observation("family-trip.mov"))
        assert result is not None
        self.assertEqual(result.kind, "media")

    def test_text_file_is_not_prefiltered(self) -> None:
        self.assertIsNone(classify_file.prefilter(self._observation("everest-problems.md")))

    def test_directory_is_not_prefiltered(self) -> None:
        observation = self._observation("some-dir")
        observation["is_dir"] = True
        self.assertIsNone(classify_file.prefilter(observation))


class CatalogAndLinearLoadTests(unittest.TestCase):
    def test_missing_catalog_path_fails_open(self) -> None:
        self.assertEqual(classify_file.load_catalog("/nonexistent/repo-catalog.json"), [])

    def test_empty_catalog_flag_fails_open(self) -> None:
        self.assertEqual(classify_file.load_catalog(""), [])

    def test_malformed_catalog_fails_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "repo-catalog.json"
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(classify_file.load_catalog(str(path)), [])

    def test_catalog_with_repos_key_loads_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "repo-catalog.json"
            path.write_text(
                json.dumps({"repos": [{"full_name": "zachbornheimer/agentmux"}]}),
                encoding="utf-8",
            )
            entries = classify_file.load_catalog(str(path))
            self.assertEqual(entries, [{"full_name": "zachbornheimer/agentmux"}])

    def test_linear_projects_accepts_plain_strings(self) -> None:
        projects = classify_file.load_linear_projects(json.dumps(["ZAP Protocol"]))
        self.assertEqual(projects, [{"name": "ZAP Protocol"}])

    def test_linear_projects_malformed_json_fails_open(self) -> None:
        self.assertEqual(classify_file.load_linear_projects("{not json"), [])

    def test_linear_projects_empty_string_fails_open(self) -> None:
        self.assertEqual(classify_file.load_linear_projects(""), [])


class BuildRequestTests(unittest.TestCase):
    """One batched request per file (typesafe-skills rule 4): per-candidate relevance
    Nouls, a kind Choice, and the 5 disposition flag Nouls — never a Choice across the
    whole catalog, and never a disposition Choice (design section 4.1: disposition is
    computed by decide(), not asked)."""

    def test_offers_one_noul_per_shortlisted_candidate(self) -> None:
        observation = observation_for("agentmux-ui-research-pass.md")
        request = classify_file.build_request(observation, SAMPLE_CATALOG, SAMPLE_LINEAR_PROJECTS)
        shortlist = classify_file._shortlist(observation, SAMPLE_CATALOG, SAMPLE_LINEAR_PROJECTS)
        noul_questions = [q for q in request["questions"] if q.startswith("match_")]
        self.assertEqual(len(noul_questions), len(shortlist))
        for question in request["questions"].values():
            self.assertIn(question["type"], {"noul", "choice"})

    def test_single_request_never_more_than_one_call_worth_of_questions(self) -> None:
        # Structural proof there is exactly one state/questions payload per file, not
        # a sequence of calls: kind and the flags ride with the project Nouls.
        observation = observation_for("agentmux-ui-research-pass.md")
        request = classify_file.build_request(observation, SAMPLE_CATALOG, [])
        self.assertIn("kind", request["questions"])
        self.assertNotIn("disposition", request["questions"])
        for flag_id in constants.FILE_FLAGS:
            self.assertIn(flag_id, request["questions"])
        self.assertTrue(any(q.startswith("match_") for q in request["questions"]))

    def test_disposition_is_never_offered_as_a_choice(self) -> None:
        # Disposition is computed in decide() from project/kind/flags, never asked —
        # this is the structural fix for "the model picks disposition before the
        # project is known" (design section 0).
        observation = observation_for("agentmux-ui-research-pass.md")
        request = classify_file.build_request(observation, [], [])
        self.assertNotIn("disposition", request["questions"])

    def test_offers_all_5_disposition_flag_nouls(self) -> None:
        observation = observation_for("agentmux-ui-research-pass.md")
        request = classify_file.build_request(observation, [], [])
        for flag_id in constants.FILE_FLAGS:
            self.assertEqual(request["questions"][flag_id]["type"], "noul")

    def test_pre_decided_project_skips_candidate_nouls(self) -> None:
        observation = observation_for("agentmux-ui-research-pass.md")
        request = classify_file.build_request(
            observation, SAMPLE_CATALOG, SAMPLE_LINEAR_PROJECTS, project="zachbornheimer/agentmux"
        )
        self.assertFalse(any(q.startswith("match_") for q in request["questions"]))
        self.assertEqual(request["state"]["project"], "zachbornheimer/agentmux")

    def test_pre_decided_project_still_asks_kind_and_flags(self) -> None:
        # Only project Nouls are skipped — kind and the 5 flags are still needed to
        # compute the disposition even when project is already known.
        observation = observation_for("2025-taxes.pdf")
        request = classify_file.build_request(observation, [], [], project="personal:finance")
        self.assertIn("kind", request["questions"])
        for flag_id in constants.FILE_FLAGS:
            self.assertIn(flag_id, request["questions"])


class DecideTests(unittest.TestCase):
    def _observation(self) -> dict:
        return observation_for("agentmux-notes.md", excerpt="notes")

    def test_winning_candidate_above_threshold_becomes_project(self) -> None:
        observation = self._observation()
        answers = answers_for(
            observation, SAMPLE_CATALOG, [], matches={"zachbornheimer/agentmux": 0.9}
        )
        result = classify_file.decide(answers, observation, SAMPLE_CATALOG, [])
        self.assertEqual(result.project, "zachbornheimer/agentmux")
        self.assertEqual(result.disposition, "move-to-repo")
        self.assertEqual(result.reason, "selected")

    def test_no_candidate_above_threshold_falls_back_to_none(self) -> None:
        observation = observation_for("random-desktop-notes.md")
        answers = answers_for(observation, SAMPLE_CATALOG, [], matches={})
        result = classify_file.decide(answers, observation, SAMPLE_CATALOG, [])
        self.assertEqual(result.project, "none")
        self.assertEqual(result.disposition, "keep")

    def test_move_to_repo_never_paired_with_non_repo_project(self) -> None:
        """Regression for the live bug: NAS-Rebuild-Plan.md classified as
        project=personal:other, disposition=move-to-repo — an incoherent pair. The
        rule chain in decide() can no longer produce this pair by construction (R4
        requires a repo project); this proves it end to end with real flag inputs."""
        observation = observation_for("NAS-Rebuild-Plan.md")
        answers = answers_for(observation, [], [], matches={"personal:other": 0.9}, kind="document")
        result = classify_file.decide(answers, observation, [], [])
        self.assertNotEqual(result.disposition, "move-to-repo")

    def test_illegal_pair_from_the_rule_chain_falls_open(self) -> None:
        # Isolates the legality-gate wrapper in decide() (typesafe-skills rule 8): the
        # rule chain is designed so it can never emit an illegal pair itself, but the
        # gate must still catch one if it ever did, as a safety net.
        observation = observation_for("2025-taxes.pdf")
        answers = answers_for(observation, [], [], matches={"personal:finance": 0.9})
        with mock.patch.object(
            classify_file,
            "_resolve_disposition",
            return_value=classify_file._DispositionOutcome("move-to-repo", 0.9, "selected"),
        ):
            result = classify_file.decide(answers, observation, [], [])
        self.assertEqual(result.project, "personal:finance")
        self.assertEqual(result.disposition, "keep")
        self.assertEqual(result.reason, "disposition illegal for project type")

    def test_kind_outside_closed_set_raises(self) -> None:
        observation = self._observation()
        answers = answers_for(observation, [], [], kind="not-a-kind")
        with self.assertRaises(ValueError):
            classify_file.decide(answers, observation, [], [])

    def test_personal_bucket_destination_is_documents(self) -> None:
        observation = observation_for("2025-taxes.pdf")
        answers = answers_for(
            observation, [], [], matches={"personal:finance": 0.9}, kind="document"
        )
        result = classify_file.decide(answers, observation, [], [])
        self.assertEqual(result.disposition, "personal-docs")
        self.assertEqual(result.destination_hint, "~/Documents/Finance")

    def test_trash_candidate_has_no_destination(self) -> None:
        observation = self._observation()
        answers = answers_for(observation, [], [], kind="backup", backup=0.95, regenerable=0.9)
        result = classify_file.decide(answers, observation, [], [])
        self.assertEqual(result.disposition, "trash-candidate")
        self.assertEqual(result.destination_hint, "")

    def test_pre_decided_project_is_used_directly(self) -> None:
        observation = self._observation()
        answers = answers_for(observation, SAMPLE_CATALOG, [])
        result = classify_file.decide(
            answers, observation, SAMPLE_CATALOG, [], project="zachbornheimer/agentmux"
        )
        self.assertEqual(result.project, "zachbornheimer/agentmux")
        self.assertEqual(result.disposition, "move-to-repo")


class GateByConsequenceTests(unittest.TestCase):
    """Rule 8: gate by consequence, not one blanket min(). Each disposition has its
    own confidence floor; low-stakes keep needs none."""

    def test_archive_fallback_matches_the_project_match_confidence(self) -> None:
        # A resolved repo project whose kind never qualifies for move-to-repo (R4)
        # falls to the R8 archive fallback (design section 4.1) at the same
        # confidence as the project match.
        observation = observation_for("agentmux-notes.md")
        answers = answers_for(
            observation,
            SAMPLE_CATALOG,
            [],
            matches={"zachbornheimer/agentmux": 0.56},
            kind="scratch",
        )
        result = classify_file.decide(answers, observation, SAMPLE_CATALOG, [])
        self.assertEqual(result.disposition, "archive")
        self.assertAlmostEqual(result.confidence, 0.56)

    def test_confidence_below_its_floor_falls_open(self) -> None:
        # Isolates the floor-gate wrapper in decide() from _resolve_disposition's
        # rule chain: every rule's own component gates (FILE_PROJECT_MATCH_THRESHOLD
        # 0.55, FILE_FLAG_FLOORS) already exceed today's disposition floors, so no
        # realistic flag input can land below them end-to-end. The gate itself still
        # must fire as designed (design section 4.1) when a disposition is below its
        # floor, so we exercise it directly for defense-in-depth.
        observation = observation_for("agentmux-notes.md")
        answers = answers_for(observation, [], [])
        with mock.patch.object(
            classify_file,
            "_resolve_disposition",
            return_value=classify_file._DispositionOutcome("move-to-repo", 0.10, "selected"),
        ):
            result = classify_file.decide(answers, observation, [], [], project="owner/repo")
        self.assertEqual(result.disposition, "keep")
        self.assertEqual(result.reason, "confidence below floor")
        self.assertFalse(result.needs_triage)

    def test_keep_never_needs_a_confidence_floor(self) -> None:
        observation = observation_for("random-desktop-notes.md")
        answers = answers_for(observation, [], [])
        result = classify_file.decide(answers, observation, [], [])
        self.assertEqual(result.disposition, "keep")
        self.assertEqual(result.reason, "selected")

    def test_thresholds_are_centralized_in_constants(self) -> None:
        self.assertEqual(
            set(constants.FILE_DISPOSITION_CONFIDENCE_FLOORS), set(constants.FILE_DISPOSITIONS)
        )


class LegalDispositionInvariantTests(unittest.TestCase):
    def test_project_kind_classifies_buckets(self) -> None:
        self.assertEqual(classify_file.project_kind("none"), "none")
        self.assertEqual(classify_file.project_kind("linear:ZAP Protocol"), "linear")
        self.assertEqual(classify_file.project_kind("personal:finance"), "personal")
        self.assertEqual(classify_file.project_kind("zachbornheimer/agentmux"), "repo")

    def test_move_to_repo_is_illegal_for_every_non_repo_project_kind(self) -> None:
        for project in ("none", "linear:ZAP Protocol", "personal:finance"):
            with self.subTest(project=project):
                self.assertNotIn("move-to-repo", classify_file.legal_dispositions_for(project))

    def test_personal_docs_is_illegal_outside_personal_projects(self) -> None:
        for project in ("none", "linear:ZAP Protocol", "zachbornheimer/agentmux"):
            with self.subTest(project=project):
                self.assertNotIn("personal-docs", classify_file.legal_dispositions_for(project))

    def test_keep_and_archive_and_trash_candidate_are_always_legal(self) -> None:
        for project in ("none", "linear:x", "personal:finance", "owner/repo"):
            legal = classify_file.legal_dispositions_for(project)
            for always_legal in ("keep", "archive", "trash-candidate"):
                with self.subTest(project=project, disposition=always_legal):
                    self.assertIn(always_legal, legal)

    def test_attach_evidence_is_legal_only_for_repo_and_linear_projects(self) -> None:
        for project in ("owner/repo", "linear:ZAP Protocol"):
            with self.subTest(project=project):
                self.assertIn("attach-evidence", classify_file.legal_dispositions_for(project))
        for project in ("none", "personal:finance"):
            with self.subTest(project=project):
                self.assertNotIn("attach-evidence", classify_file.legal_dispositions_for(project))


class DispositionLegalityPropertyTests(unittest.TestCase):
    """Design section 3.5's property test, mapped onto flat project kinds: every
    project kind x every file kind x a flag grid always yields a legal disposition,
    and private data or a loss record (>= 0.5) never yields trash."""

    FLAG_GRID = (0.1, 0.5, 0.9)
    PROJECTS = ("none", "linear:ZAP Protocol", "personal:finance", "owner/repo")

    def test_every_combination_yields_a_legal_disposition_and_never_trashes_private_data(
        self,
    ) -> None:
        observation = observation_for("grid-fixture.md")
        catalog_entries = [
            {"full_name": "owner/repo", "keywords": [], "local_path": "/tmp/owner-repo"}
        ]
        for project in self.PROJECTS:
            for kind in constants.FILE_KINDS:
                for backup in self.FLAG_GRID:
                    for issue_list in self.FLAG_GRID:
                        for evidence in self.FLAG_GRID:
                            for private in self.FLAG_GRID:
                                for regenerable in self.FLAG_GRID:
                                    for loss_record in self.FLAG_GRID:
                                        answers = answers_for(
                                            observation,
                                            [],
                                            [],
                                            kind=kind,
                                            backup=backup,
                                            issue_list=issue_list,
                                            evidence=evidence,
                                            private=private,
                                            regenerable=regenerable,
                                            loss_record=loss_record,
                                        )
                                        result = classify_file.decide(
                                            answers,
                                            observation,
                                            catalog_entries,
                                            [],
                                            project=project,
                                        )
                                        with self.subTest(
                                            project=project,
                                            kind=kind,
                                            backup=backup,
                                            issue_list=issue_list,
                                            evidence=evidence,
                                            private=private,
                                            regenerable=regenerable,
                                            loss_record=loss_record,
                                        ):
                                            self.assertIn(
                                                result.disposition,
                                                classify_file.legal_dispositions_for(project),
                                            )
                                            if private >= 0.5 or loss_record >= 0.5:
                                                self.assertNotEqual(
                                                    result.disposition, "trash-candidate"
                                                )


def run_classify_file(
    paths: list[str],
    *,
    catalog: str = "",
    linear_projects: str = "",
    getenv=getenv_with_key,
    urlopen=None,
    read_keychain=None,
) -> tuple[int, list[dict], str]:
    stdout = io.StringIO()
    keychain = read_keychain if read_keychain is not None else (lambda: None)
    argv = ["classify-file", *paths]
    if catalog:
        argv += ["--catalog", catalog]
    if linear_projects:
        argv += ["--linear-projects", linear_projects]
    with redirect_stdout(stdout):
        code = cli.main(
            argv,
            getenv=getenv,
            urlopen=urlopen,
            read_keychain=keychain,
            stdin=io.StringIO(""),
            stdout=stdout,
        )
    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    return code, lines, stdout.getvalue()


def single_call_payload(
    observation: dict,
    catalog_entries: list[dict],
    linear_projects: list[dict],
    *,
    matches: dict[str, float] | None = None,
    kind: str = "spec",
    backup: float = 0.0,
    issue_list: float = 0.0,
    evidence: float = 0.0,
    private: float = 0.0,
    regenerable: float = 0.0,
    loss_record: float = 0.0,
) -> dict:
    return {
        "answers": answers_for(
            observation,
            catalog_entries,
            linear_projects,
            matches=matches,
            kind=kind,
            backup=backup,
            issue_list=issue_list,
            evidence=evidence,
            private=private,
            regenerable=regenerable,
            loss_record=loss_record,
        ),
        "usage": {"input_tokens": 80, "output_tokens": 12},
    }


class NamedDesktopFixtureRedCaseTests(unittest.TestCase):
    """Design section 7's named Desktop fixtures — RED against the pre-S2 bug (the
    disposition Choice trashed private/irreplaceable data and could not route issue
    lists or evidence without a project) and GREEN against the flag-based rule
    chain, including the F1/F2 triage defaults."""

    def test_mail_import_backup_is_never_trashed_and_the_reason_shows_the_private_guard(
        self,
    ) -> None:
        # entries=["Import.mbox"]: irreplaceable mail, not a recreatable export.
        observation = observation_for("mail-import-backup")
        observation["is_dir"] = True
        observation["entries"] = ["Import.mbox"]
        answers = answers_for(
            observation, [], [], kind="backup", backup=0.95, private=0.9, regenerable=0.1
        )
        result = classify_file.decide(answers, observation, [], [])
        self.assertNotEqual(result.disposition, "trash-candidate")
        self.assertEqual(result.reason, "private data blocks trash")

    def test_dorico_diagnostics_zip_is_never_trashed(self) -> None:
        # entries include Activation Manager/.../config.dat + settings.json: license
        # data, not disposable diagnostics.
        observation = observation_for("Dorico Diagnostics.zip")
        observation["entries"] = ["Activation Manager/config.dat", "settings.json"]
        answers = answers_for(observation, [], [], kind="evidence", evidence=0.8, private=0.7)
        result = classify_file.decide(answers, observation, [], [])
        self.assertNotEqual(result.disposition, "trash-candidate")
        self.assertEqual(result.disposition, "keep")
        self.assertEqual(result.reason, "evidence: needs project triage")
        self.assertTrue(result.needs_triage)

    def test_hof_backup_preconvert_html_still_trashes_a_real_backup(self) -> None:
        # Guards against over-correction: a genuinely regenerable, non-private backup
        # must still reach trash-candidate.
        observation = observation_for("hof-25162-backup-preconvert.html")
        answers = answers_for(
            observation, [], [], kind="backup", backup=0.95, regenerable=0.9, private=0.05
        )
        result = classify_file.decide(answers, observation, [], [])
        self.assertEqual(result.disposition, "trash-candidate")

    def test_flight_fix_list_routes_to_linear_via_its_repos_linear_sibling(self) -> None:
        # The shortlist only ever offers "zysys/flight" (a Linear project sharing a
        # repo's basename is shadowed, see _shortlist) — the fix is that decide()
        # discovers flight's Linear sibling from the resolved repo project, so an
        # issue list still reaches file-to-linear instead of illegal/move-to-repo.
        observation = observation_for("flight-fix-list.md")
        answers = answers_for(
            observation,
            SAMPLE_CATALOG,
            SAMPLE_LINEAR_PROJECTS,
            matches={"zysys/flight": 0.85},
            kind="issue-list",
            issue_list=0.85,
        )
        result = classify_file.decide(answers, observation, SAMPLE_CATALOG, SAMPLE_LINEAR_PROJECTS)
        self.assertEqual(result.project, "zysys/flight")
        self.assertEqual(result.disposition, "file-to-linear")
        self.assertNotEqual(result.reason, "disposition illegal for project type")

    def test_obsidian_live_proof_needs_regenerable_not_just_backup_to_trash(self) -> None:
        # flag_backup low (not a duplicate) even though flag_regenerable is high: R2
        # now requires both signals, so a low backup flag alone blocks trash.
        observation = observation_for("obsidian-live-proof-20260713-101402.txt")
        answers = answers_for(
            observation, [], [], kind="evidence", backup=0.2, regenerable=0.9, evidence=0.8
        )
        result = classify_file.decide(answers, observation, [], [])
        self.assertNotEqual(result.disposition, "trash-candidate")
        self.assertEqual(result.disposition, "keep")
        self.assertEqual(result.reason, "evidence: needs project triage")

    def test_navidrome_missing_files_csv_is_never_trashed(self) -> None:
        # Live case (Zach, 2026-09-24): a NAS data-loss recovery inventory of which
        # files are missing -- the model was tempted to trash it as a "data-dump"
        # (backup+regenerable both high, mirroring the pre-fix run). It is the only
        # record of what was lost, so flag_loss_record must block trash regardless.
        observation = observation_for(
            "navidrome_missing_files.csv", excerpt="path,artist,album\n/music/a.flac,A,B\n"
        )
        answers = answers_for(
            observation,
            [],
            [],
            kind="data-dump",
            backup=0.85,
            regenerable=0.85,
            loss_record=0.9,
        )
        result = classify_file.decide(answers, observation, [], [])
        self.assertNotEqual(result.disposition, "trash-candidate")
        self.assertEqual(result.reason, "loss record blocks trash")
        self.assertTrue(result.important)

    def test_lidarr_csv_coverage_jsonl_is_never_trashed(self) -> None:
        observation = observation_for(
            "lidarr-csv-coverage.jsonl", excerpt='{"artist": "A", "covered": false}\n'
        )
        answers = answers_for(
            observation,
            [],
            [],
            kind="data-dump",
            backup=0.85,
            regenerable=0.85,
            loss_record=0.85,
        )
        result = classify_file.decide(answers, observation, [], [])
        self.assertNotEqual(result.disposition, "trash-candidate")
        self.assertEqual(result.reason, "loss record blocks trash")
        self.assertTrue(result.important)

    def test_loss_record_at_its_own_repo_routes_to_move_to_repo(self) -> None:
        # Once trash is blocked, the rule chain continues: a loss record that also
        # resolves to its owning repo (design: "route to its resolved product") still
        # reaches move-to-repo rather than stalling at keep.
        nas_recovery_catalog = [
            {
                "full_name": "zachbornheimer/nas-recovery",
                "keywords": ["nas-recovery", "carve-reconcile"],
                "local_path": "/tmp/nas-recovery",
            }
        ]
        observation = observation_for(
            "nas-recovery-coverage.jsonl", excerpt='{"artist": "A", "covered": false}\n'
        )
        answers = answers_for(
            observation,
            nas_recovery_catalog,
            [],
            matches={"zachbornheimer/nas-recovery": 0.9},
            kind="data-dump",
            backup=0.85,
            regenerable=0.85,
            loss_record=0.85,
        )
        result = classify_file.decide(answers, observation, nas_recovery_catalog, [])
        self.assertEqual(result.project, "zachbornheimer/nas-recovery")
        self.assertEqual(result.disposition, "move-to-repo")
        self.assertTrue(result.important)

    def test_hof_backup_preconvert_html_with_no_loss_record_signal_still_trashes(self) -> None:
        # Guard against over-correction: a genuinely regenerable backup with no loss
        # record signal must still reach trash-candidate, and `important` stays False.
        observation = observation_for("hof-25162-backup-preconvert.html")
        answers = answers_for(
            observation,
            [],
            [],
            kind="backup",
            backup=0.95,
            regenerable=0.9,
            private=0.05,
            loss_record=0.05,
        )
        result = classify_file.decide(answers, observation, [], [])
        self.assertEqual(result.disposition, "trash-candidate")
        self.assertFalse(result.important)

    def test_loss_record_filename_tokens_raise_the_state_hint(self) -> None:
        for filename in (
            "navidrome_missing_files.csv",
            "lidarr-csv-coverage.jsonl",
            "recovery-lost-files.json",
        ):
            with self.subTest(filename=filename):
                observation = observation_for(filename)
                request = classify_file.build_request(observation, [], [])
                self.assertTrue(request["state"]["loss_record_hint"])

    def test_unrelated_filename_does_not_raise_the_loss_record_hint(self) -> None:
        observation = observation_for("hof-25162-backup-preconvert.html")
        request = classify_file.build_request(observation, [], [])
        self.assertFalse(request["state"]["loss_record_hint"])


class ClassifyFileCliTests(unittest.TestCase):
    def test_prefiltered_backup_skips_http(self) -> None:
        urlopen = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.bkup"
            path.write_text("x", encoding="utf-8")
            code, results, _raw = run_classify_file([str(path)], urlopen=urlopen)
            self.assertEqual(code, 0)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["disposition"], "trash-candidate")
        urlopen.assert_not_called()

    def test_missing_path_falls_open(self) -> None:
        code, results, _raw = run_classify_file(["/nonexistent/nope.md"])
        self.assertEqual(code, 0)
        self.assertEqual(results[0]["project"], "none")
        self.assertEqual(results[0]["reason"], "path not found")

    def test_missing_key_falls_open_without_http(self) -> None:
        urlopen = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "everest-problems.md"
            path.write_text("mountain climbing plan", encoding="utf-8")
            code, results, stderr = run_classify_file(
                [str(path)], getenv=getenv_without_key, urlopen=urlopen
            )
            self.assertEqual(code, 0)
            self.assertEqual(results[0]["disposition"], "keep")
            self.assertNotIn(SECRET, stderr)
        urlopen.assert_not_called()

    def test_one_http_call_per_file_produces_one_json_line_each(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            catalog_path = Path(tmp) / "repo-catalog.json"
            catalog_path.write_text(json.dumps({"repos": SAMPLE_CATALOG}), encoding="utf-8")
            first = Path(tmp) / "agentmux-ui-research-pass.md"
            first.write_text("design notes for agentmux", encoding="utf-8")
            second = Path(tmp) / "2025-taxes.pdf"
            second.write_bytes(b"not a real pdf")

            second_observation = classify_file.observe(
                second, run_pdftotext=lambda p: "household 2025 tax filing"
            )
            urlopen = mock.Mock(
                side_effect=[
                    # first: strong_project_match resolves "agentmux" deterministically,
                    # so this call only carries kind/flags, not project Nouls.
                    FakeHTTPResponse(
                        {
                            "answers": {
                                "kind": choice_answer("spec", 0.9),
                                **flag_answers(),
                            },
                            "usage": {},
                        }
                    ),
                    FakeHTTPResponse(
                        single_call_payload(
                            second_observation,
                            [],
                            [],
                            matches={"personal:finance": 0.9},
                            kind="document",
                        )
                    ),
                ]
            )
            code, results, _raw = run_classify_file(
                [str(first), str(second)], catalog=str(catalog_path), urlopen=urlopen
            )
            self.assertEqual(code, 0)
            self.assertEqual(len(results), 2)
            self.assertEqual(urlopen.call_count, 2)  # one request per file, not two
            self.assertEqual(results[0]["project"], "zachbornheimer/agentmux")
            self.assertEqual(results[1]["project"], "personal:finance")

    def test_move_to_repo_never_shipped_for_a_personal_project_end_to_end(self) -> None:
        """End-to-end regression: NAS-Rebuild-Plan.md used to classify as
        project=personal:other, disposition=move-to-repo — an incoherent pair. The
        rule chain now computes a legal disposition for the resolved project by
        construction (personal-docs, not move-to-repo)."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "NAS-Rebuild-Plan.md"
            path.write_text("plan for rebuilding the NAS", encoding="utf-8")
            observation = classify_file.observe(path)
            urlopen = mock.Mock(
                return_value=FakeHTTPResponse(
                    single_call_payload(
                        observation,
                        [],
                        [],
                        matches={"personal:other": 0.9},
                        kind="document",
                    )
                )
            )
            code, results, _raw = run_classify_file([str(path)], urlopen=urlopen)
            self.assertEqual(code, 0)
            self.assertNotEqual(results[0]["disposition"], "move-to-repo")
            self.assertEqual(results[0]["disposition"], "personal-docs")

    def test_never_writes_or_deletes_the_classified_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.bkup"
            path.write_text("original", encoding="utf-8")
            run_classify_file([str(path)])
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), "original")


if __name__ == "__main__":
    unittest.main()
