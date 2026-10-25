"""Public JSON and TypeSafe protocol values."""

from __future__ import annotations

MODEL = "jev-latest"
LOCAL_BASE_URL = "http://localhost:11434"
HOSTED_BASE_URL = "https://api.typesafe.ai"
OPENROUTER_BASE_URL = "https://openrouter.ai/api"
# Tried in order; a failure (429, timeout, down) falls through to the next.
# OpenRouter bills the same Jev model to an OpenRouter account and is skipped when no
# OpenRouter key exists. Hosted next: local jev disagreed with hosted on 4 of 8 picks (2026-10-14).
BASE_URLS = (OPENROUTER_BASE_URL, HOSTED_BASE_URL, LOCAL_BASE_URL)
# Each base names the model its own way; hosted keeps the payload's model.
MODEL_BY_BASE_URL = {
    LOCAL_BASE_URL: "jev-1.13.0:latest",
    OPENROUTER_BASE_URL: "typesafe/jev-1.14",
}
SYSTEMONE_PATH = "/v1/systemone"
BASE_URL_ENV = "TYPESAFE_BASE_URL"
API_KEY_ENV = "TYPESAFE_API_KEY"
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
KEYCHAIN_SERVICE = "typesafe-api-key"
OPENROUTER_KEYCHAIN_SERVICE = "openrouter-api-key"
REQUEST_TIMEOUT_SECONDS = 2.0
KEYCHAIN_TIMEOUT_SECONDS = 2.0
DESCRIPTION_CHARS = 180
# pick-skill follows TypeSafe's skill-suggestion cookbook: a wide rank gated by
# three request nouls, then a rerank of the shortlist on SKILL.md excerpts.
# NEEDS_SKILL_THRESHOLD gates the noul mean; PICK_FITS_THRESHOLD gates the winner's fit.
# Tuned on hosted jev over 133 labeled prompts (2026-10-14): 0/99 wrong, 1/34 needless.
# The cookbook's 0.30 gate rejected 11 advisory skills (spec-writer, seo-plan, api, ...)
# whose requests a generalist could answer in prose; the fit check catches those instead.
NEEDS_SKILL_THRESHOLD = 0.10
PICK_FITS_THRESHOLD = 0.50
PICK_SHORTLIST = 3
PICK_EXCERPT_CHARS = 700
# Most options one Choice may carry, by base URL; each roster chunk keeps one for "none".
PICK_CHOICE_MAX_OPTIONS = 255
PICK_CHOICE_MAX_OPTIONS_BY_BASE_URL = {LOCAL_BASE_URL: 26}
REASON_NO_FIT = "no shortlisted skill fits"
REASON_RERANK_FAILED = "rerank failed"
SECOND_PRODUCT_THRESHOLD = 0.85
QUESTION_SECOND_PRODUCT = "second_product"
QUESTION_SESSION_RELATION = "session_relation"
IN_FLIGHT_NONE = "none"
SESSION_SPLIT_CONFIDENCE_FLOOR = 0.50
SESSION_RELATION_TOP_LEVEL = 2
SESSION_RELATION_LEVELS = (
    {
        "what": ("Same work: continue, correct, first ask, or small talk about `in_flight`."),
        "examples": [
            "keep going on the current task",
            "fix that typo in the in-flight change",
            "first ask while `in_flight` is none",
            "small talk about the open work",
        ],
    },
    {
        "what": "Related, but could reasonably be its own session.",
        "examples": [
            "adjacent cleanup that could wait",
            "a follow-on in the same area, optional now",
        ],
    },
    {
        "what": "Distinct user-visible outcome, even in the same repo.",
        "examples": [
            'person-menu Gravatar/sign-out vs "Sync Mac licks to iPad"',
            '"also land zq live" while evo is in flight',
            "a second Linear id",
        ],
    },
)
CLASSIFY_SESSION_FLOOR = 50
SOURCE_TYPESAFE = "typesafe"
SOURCE_FALLBACK = "fallback"
CHOICE_NONE = "none"
ACTION_FILE_NEW = "file_new"
ACTION_FALSE_POSITIVE = "false_positive"
ACTION_NO_CHANGE = "no_change"
JOIN_PREFIX = "join_"
PRIMITIVES = ("command", "skill", "hook", "subagent", "removal", "none")
ALWAYS_CLASSIFY_KINDS = frozenset(
    {
        "retry",
        "long_session",
        "permission_stop",
        "instruction_bloat",
        "model_routing",
        "subagent",
    }
)
SKILL_ROOTS = (".agents/skills", ".agents/available-skills", ".grok/skills")
SELECTOR_GROUPS = (
    ("bar", ("review-bar",), ("review-bar",)),
    (
        "skill-creator",
        ("create-skill", "skill-design-principles"),
        ("skill-design-principles",),
    ),
    ("pr-review", ("review",), ()),
    ("assume-session", ("find-session",), ("find-session",)),
    ("api", ("api-docs",), ("api-docs",)),
    ("diagnose", ("debug-protocol",), ("debug-protocol",)),
)
REASON_UNAVAILABLE = "typesafe unavailable"
REASON_MISSING_KEY = "missing key"
REASON_TIMEOUT = "timeout"
REASON_BELOW_THRESHOLD = "needs_skill below threshold"
REASON_BELOW_CONFIDENCE = "confidence below floor"
REASON_IN_SCOPE_BELOW_FLOOR = "in_scope below floor"
REASON_NONE = "no skill"
REASON_SELECTED = "selected"
ISJAC_CONFIDENCE_FLOOR = 0.55
ISJAC_IN_SCOPE_FLOOR = 0.50
TICKET_CONFIDENCE_FLOOR = 0.50
ONCALL_CONFIDENCE_FLOOR = 0.60
ISJAC_KIND_PRODUCT_BUG = "product_bug"
ISJAC_KIND_OPS_SKIP = "ops_skip"
ISJAC_KIND_NOISE = "noise"
ISJAC_KIND_UNKNOWN = "unknown"
ISJAC_KINDS = (ISJAC_KIND_PRODUCT_BUG, ISJAC_KIND_OPS_SKIP, ISJAC_KIND_NOISE)
TICKET_TYPE_FEATURE = "feature"
TICKET_TYPE_BUG = "bug"
TICKET_TYPE_IMPROVEMENT = "improvement"
TICKET_TYPE_CLOUD = "cloud"
TICKET_TYPE_SPEC = "spec"
TICKET_TYPE_OTHER = "other"
TICKET_TYPE_UNKNOWN = "unknown"
TICKET_ISSUE_TYPES = (
    TICKET_TYPE_FEATURE,
    TICKET_TYPE_BUG,
    TICKET_TYPE_IMPROVEMENT,
    TICKET_TYPE_CLOUD,
    TICKET_TYPE_SPEC,
    TICKET_TYPE_OTHER,
)
TICKET_PRIORITY_NONE = 0
TICKET_PRIORITY_NUMBERS = {"p1": 1, "p2": 2, "p3": 3, "p4": 4}
TICKET_PRIORITIES = tuple(TICKET_PRIORITY_NUMBERS)
ONCALL_DISPOSITION_FALSE_POSITIVE = "false_positive"
ONCALL_DISPOSITION_REAL = "real"
ONCALL_DISPOSITION_NOISE = "noise"
ONCALL_DISPOSITION_UNKNOWN = "unknown"
ONCALL_DISPOSITIONS = (
    ONCALL_DISPOSITION_FALSE_POSITIVE,
    ONCALL_DISPOSITION_REAL,
    ONCALL_DISPOSITION_NOISE,
)
ONCALL_CAUSE_APP_BUG = "app_bug"
ONCALL_CAUSE_INFRA_FAILURE = "infra_failure"
ONCALL_CAUSE_ALERT_MISCONFIG = "alert_misconfig"
ONCALL_CAUSE_UNKNOWN = "unknown"
ONCALL_CAUSE_CLASSES = (
    ONCALL_CAUSE_APP_BUG,
    ONCALL_CAUSE_INFRA_FAILURE,
    ONCALL_CAUSE_ALERT_MISCONFIG,
    ONCALL_CAUSE_UNKNOWN,
)
ONCALL_SEV1 = "sev1"
ONCALL_SEV2 = "sev2"
ONCALL_SEV3 = "sev3"
ONCALL_SEV_NONE = "none"
ONCALL_SEVS = (ONCALL_SEV1, ONCALL_SEV2, ONCALL_SEV3, ONCALL_SEV_NONE)
ONCALL_BAND_LOW = "low"
ONCALL_BAND_MEDIUM = "medium"
ONCALL_BAND_HIGH = "high"
ONCALL_BANDS = (ONCALL_BAND_LOW, ONCALL_BAND_MEDIUM, ONCALL_BAND_HIGH)
FILE_KIND_SPEC = "spec"
FILE_KIND_ISSUE_LIST = "issue-list"
FILE_KIND_EVIDENCE = "evidence"
FILE_KIND_DATA_DUMP = "data-dump"
FILE_KIND_SCRIPT = "script"
FILE_KIND_SCREENSHOT = "screenshot"
FILE_KIND_MEDIA = "media"
FILE_KIND_DOCUMENT = "document"
FILE_KIND_BACKUP = "backup"
FILE_KIND_SCRATCH = "scratch"
FILE_KINDS = (
    FILE_KIND_SPEC,
    FILE_KIND_ISSUE_LIST,
    FILE_KIND_EVIDENCE,
    FILE_KIND_DATA_DUMP,
    FILE_KIND_SCRIPT,
    FILE_KIND_SCREENSHOT,
    FILE_KIND_MEDIA,
    FILE_KIND_DOCUMENT,
    FILE_KIND_BACKUP,
    FILE_KIND_SCRATCH,
)
FILE_DISPOSITION_MOVE_TO_REPO = "move-to-repo"
FILE_DISPOSITION_FILE_TO_LINEAR = "file-to-linear"
FILE_DISPOSITION_ARCHIVE = "archive"
FILE_DISPOSITION_PERSONAL_DOCS = "personal-docs"
FILE_DISPOSITION_TRASH_CANDIDATE = "trash-candidate"
FILE_DISPOSITION_KEEP = "keep"
# F1 (Zach, 2026-09-23): evidence is uploaded to Linear as an issue attachment rather
# than archived or left in place. "Attach" is deliberately distinct from
# "file-to-linear" (which turns an issue *list* into a new ticket) -- this disposition
# never creates a ticket, only attaches proof to one that already exists.
FILE_DISPOSITION_ATTACH_EVIDENCE = "attach-evidence"
FILE_DISPOSITIONS = (
    FILE_DISPOSITION_MOVE_TO_REPO,
    FILE_DISPOSITION_FILE_TO_LINEAR,
    FILE_DISPOSITION_ARCHIVE,
    FILE_DISPOSITION_PERSONAL_DOCS,
    FILE_DISPOSITION_TRASH_CANDIDATE,
    FILE_DISPOSITION_KEEP,
    FILE_DISPOSITION_ATTACH_EVIDENCE,
)
FILE_PROJECT_KIND_REPO = "repo"
FILE_PROJECT_KIND_LINEAR = "linear"
FILE_PROJECT_KIND_PERSONAL = "personal"
FILE_PROJECT_KIND_NONE = "none"
FILE_LEGAL_DISPOSITIONS_BY_PROJECT_KIND = {
    FILE_PROJECT_KIND_REPO: (
        FILE_DISPOSITION_MOVE_TO_REPO,
        FILE_DISPOSITION_ARCHIVE,
        FILE_DISPOSITION_FILE_TO_LINEAR,
        FILE_DISPOSITION_TRASH_CANDIDATE,
        FILE_DISPOSITION_KEEP,
        FILE_DISPOSITION_ATTACH_EVIDENCE,
    ),
    FILE_PROJECT_KIND_LINEAR: (
        FILE_DISPOSITION_FILE_TO_LINEAR,
        FILE_DISPOSITION_ARCHIVE,
        FILE_DISPOSITION_TRASH_CANDIDATE,
        FILE_DISPOSITION_KEEP,
        FILE_DISPOSITION_ATTACH_EVIDENCE,
    ),
    FILE_PROJECT_KIND_PERSONAL: (
        FILE_DISPOSITION_PERSONAL_DOCS,
        FILE_DISPOSITION_ARCHIVE,
        FILE_DISPOSITION_TRASH_CANDIDATE,
        FILE_DISPOSITION_KEEP,
    ),
    FILE_PROJECT_KIND_NONE: (
        FILE_DISPOSITION_ARCHIVE,
        FILE_DISPOSITION_TRASH_CANDIDATE,
        FILE_DISPOSITION_KEEP,
    ),
}
REASON_FILE_ILLEGAL_DISPOSITION = "disposition illegal for project type"
FILE_PROJECT_NONE = "none"
FILE_PROJECT_PERSONAL_LIFE = "personal:life"
FILE_PROJECT_PERSONAL_FINANCE = "personal:finance"
FILE_PROJECT_PERSONAL_FAMILY = "personal:family"
FILE_PROJECT_PERSONAL_MUSIC = "personal:music"
FILE_PROJECT_PERSONAL_PAPERWORK = "personal:paperwork"
FILE_PROJECT_PERSONAL_OTHER = "personal:other"
FILE_PERSONAL_BUCKET_CRITERIA = {
    FILE_PROJECT_PERSONAL_FINANCE: "Personal finance: taxes, banking, investments.",
    FILE_PROJECT_PERSONAL_FAMILY: "Personal family or life-admin records.",
    FILE_PROJECT_PERSONAL_MUSIC: "Music scores, recordings, or composition work.",
    FILE_PROJECT_PERSONAL_PAPERWORK: "Personal paperwork: contracts, ids, receipts.",
    FILE_PROJECT_PERSONAL_LIFE: "General personal life content with no sharper bucket.",
    FILE_PROJECT_PERSONAL_OTHER: "Personal content that fits no other bucket above.",
}
FILE_DEST_FINANCE = "~/Documents/Finance"
FILE_DEST_FAMILY = "~/Documents/Family"
FILE_DEST_MUSIC = "~/Music"
FILE_DEST_PAPERWORK = "~/Documents/Paperwork"
FILE_DEST_LIFE = "~/Documents"
FILE_PERSONAL_DESTINATIONS = {
    FILE_PROJECT_PERSONAL_FINANCE: FILE_DEST_FINANCE,
    FILE_PROJECT_PERSONAL_FAMILY: FILE_DEST_FAMILY,
    FILE_PROJECT_PERSONAL_MUSIC: FILE_DEST_MUSIC,
    FILE_PROJECT_PERSONAL_PAPERWORK: FILE_DEST_PAPERWORK,
    FILE_PROJECT_PERSONAL_LIFE: FILE_DEST_LIFE,
    FILE_PROJECT_PERSONAL_OTHER: FILE_DEST_LIFE,
}
# Content cap sent to the model as `state.excerpt` — substantially more than a thin
# preview so real judgment has real evidence (text files, and extracted text from
# docx/pdf/html/zip/scriv). Bytes, read before decode.
FILE_TEXT_CONTENT_BYTES = 20_000
FILE_MAX_DIR_ENTRIES = 50
FILE_PREFILTER_CONFIDENCE = 0.90
FILE_PREFILTER_MEDIA_CONFIDENCE = 0.60
# A token/keyword shared by at most this many catalog repos is distinctive enough to
# decide `project` from the filename alone, without asking the model. Above this, the
# signal is ambiguous (e.g. "obsidian" alone names 3 repos) and must go to scoring.
FILE_STRONG_MATCH_MAX_DOCUMENT_FREQUENCY = 2
# How many scored repo/Linear candidates (plus the always-offered personal:* buckets)
# get a per-candidate relevance Noul — keeps the judged set legible instead of the
# whole catalog (165+ repos diluted a single Choice's confidence toward the floor).
FILE_PROJECT_CANDIDATE_LIMIT = 8
# Exact basename-token matches outrank keyword-only overlap of similar weight.
FILE_CATALOG_BASENAME_BONUS = 2.0
# Bound on excerpt text folded into project-matching tokens (separate from the larger
# FILE_TEXT_CONTENT_BYTES sent to the model as state).
FILE_SCORING_EXCERPT_CHARS = 500
# A candidate's per-file relevance Noul must clear this probability to become the
# resolved `project`; otherwise project falls back to "none" rather than guessing.
FILE_PROJECT_MATCH_THRESHOLD = 0.55
# Gate by consequence (typesafe-skills rule 8), not one blanket floor: a suggested
# repo move or a trash candidacy needs stronger evidence than an archive/personal-docs
# suggestion; "keep" is always reversible and needs none. Disposition is a 6-way
# Choice (uniform baseline ~0.167) — these floors were validated against a real
# Desktop run (2026-09-23, 119 files): move-to-repo/personal-docs/file-to-linear
# choices routinely land 0.35-0.65 confidence when the disposition is in fact
# correct, so a floor near the *Choice* threshold, not near certainty, is realistic.
FILE_DISPOSITION_CONFIDENCE_FLOORS = {
    FILE_DISPOSITION_MOVE_TO_REPO: 0.40,
    FILE_DISPOSITION_TRASH_CANDIDATE: 0.45,
    FILE_DISPOSITION_FILE_TO_LINEAR: 0.30,
    FILE_DISPOSITION_PERSONAL_DOCS: 0.30,
    FILE_DISPOSITION_ARCHIVE: 0.25,
    FILE_DISPOSITION_KEEP: 0.0,
    # Matches FILE_FLAG_FLOORS["evidence"] -- the same bar that gates whether the
    # flag itself counts as "evidence" also gates shipping the upload.
    FILE_DISPOSITION_ATTACH_EVIDENCE: 0.60,
}
# subprocess timeout for textutil/pdftotext text extraction.
FILE_EXTRACT_TIMEOUT_SECONDS = 5.0
# How many text-like files inside a directory/bundle (e.g. a .scriv project) get
# sampled for content, and how much of each.
FILE_DIR_SAMPLE_FILE_COUNT = 3
FILE_DIR_SAMPLE_FILE_CHARS = 2000
FILE_DIR_SAMPLE_MAX_DEPTH = 2
# Hierarchical file taxonomy (schema for organize-files/data/taxonomy.json, loaded
# and validated — never built — by taxonomy.py). Only the constants the loader/
# validator need land here; beam-search and request-shaping constants belong to the
# slice that adds them.
FILE_TAXONOMY_SCHEMA_VERSION = 1
# Root has at most this many top-level areas — keeps the area Choice legible.
FILE_TAXONOMY_MAX_AREAS = 10
REASON_FILE_TAXONOMY_INVALID = "taxonomy invalid"
# Beam search over taxonomy.json (design section 3 / typesafe-skills example 26):
# keep the top-K partial paths at each depth, ranked by the geometric mean of edge
# probabilities (length-normalized so deep and shallow paths compare fairly).
FILE_TAXONOMY_BEAM_WIDTH = 3
# At most this many batched TypeSafe calls per file: 1 on a strong match, typically 2,
# 3 only when a round-2 answer still leaves a multi-leaf product unresolved.
FILE_TAXONOMY_MAX_ROUNDS = 3
# How many top-prior areas get a speculative product@ Choice in round 1, so a
# confident area guess can resolve to a leaf without waiting for round 2.
FILE_TAXONOMY_SPECULATIVE_AREAS = 2
# Areas with more products than this are marked `large` by the builder; the request
# builder then narrows what is offered instead of asking every product (section 2.3).
FILE_TAXONOMY_FULL_CHOICE_MAX_SIBLINGS = 12
# A large area's shortlisted product Choice is padded to at least this many options
# (plus `other`) even when the IDF shortlist alone returns fewer.
FILE_TAXONOMY_LARGE_AREA_MIN_OPTIONS = 4
# Floor under a raw probability before taking its log, so a 0.0 answer never raises a
# math domain error in the geometric-mean score.
FILE_TAXONOMY_PROB_EPSILON = 1e-9
# The escape option offered on every taxonomy Choice ("none of these fits").
FILE_TAXONOMY_OTHER = "other"
# Back-off floors (design section 3): the minimum prefix mass a node needs to be the
# resolved depth. They shrink with depth because mass is a product of edge
# probabilities — retune from decisions.jsonl once labeled data exists.
FILE_TAXONOMY_DEPTH_FLOORS = {1: 0.55, 2: 0.40, 3: 0.30}
REASON_FILE_STRONG_MATCH = "strong match"
REASON_FILE_BACKOFF = "resolved above leaf"
FILE_FLAG_BACKUP = "flag_backup"
FILE_FLAG_ISSUE_LIST = "flag_issue_list"
FILE_FLAG_EVIDENCE = "flag_evidence"
FILE_FLAG_PRIVATE = "flag_private"
FILE_FLAG_REGENERABLE = "flag_regenerable"
# A loss record (Zach, 2026-09-24): an inventory of files that are missing, lost, or
# unrecovered may be the only surviving record of what was lost -- deleting it loses
# the loss itself, not just a copy. Gates trash the same way flag_private does.
FILE_FLAG_LOSS_RECORD = "flag_loss_record"
FILE_FLAGS = (
    FILE_FLAG_BACKUP,
    FILE_FLAG_ISSUE_LIST,
    FILE_FLAG_EVIDENCE,
    FILE_FLAG_PRIVATE,
    FILE_FLAG_REGENERABLE,
    FILE_FLAG_LOSS_RECORD,
)
# Thresholds the disposition rules (classify_file.decide) apply to the flag Nouls
# above. Gate by consequence (rule 8): a wrongly-suggested trash is far costlier than
# a wrongly-suggested archive, so trash needs two independent, high-bar flags plus the
# private guard, while evidence/issue-list only gate a single softer disposition.
FILE_FLAG_FLOORS = {
    "trash_backup": 0.80,
    "trash_regenerable": 0.70,
    "private_guard": 0.50,
    "issue_to_linear": 0.70,
    "evidence": 0.60,
    # Same bar as private_guard -- a possible loss record is treated as seriously as
    # possible private data, and both flip the same `important` output flag.
    "loss_record": 0.50,
}
REASON_FILE_PRIVATE_GUARD = "private data blocks trash"
REASON_FILE_LOSS_RECORD_GUARD = "loss record blocks trash"
# Filename tokens that hint a file may record lost/missing/unrecovered data (e.g. a
# NAS recovery's coverage report). A deterministic prior only -- it raises attention
# on the flag_loss_record question via `state`, it never decides the disposition
# itself; only the model's own Noul answer, gated by FILE_FLAG_FLOORS["loss_record"],
# does that.
FILE_LOSS_RECORD_FILENAME_TOKENS = frozenset({"missing", "lost", "unrecovered", "coverage"})
# F1/F2 (Zach, 2026-09-23): both forks resolved to a human-in-the-loop default rather
# than an automatic move/archive, until the deferred question is answered.
# F1: evidence for a project with a Linear home uploads there directly
# (FILE_DISPOSITION_ATTACH_EVIDENCE); evidence for a project with no Linear home is
# queued for the same triage step as an orphan issue list.
REASON_FILE_EVIDENCE_NEEDS_TRIAGE = "evidence: needs project triage"
# F2: an issue list with no Linear project to attach to is not silently moved into a
# repo's docs/ — it is queued for an agent step to read the file, work out the owning
# project, and ask Zach.
REASON_FILE_ISSUE_NEEDS_TRIAGE = "issue list: needs project triage"
REASON_FILE_BACKUP_PATTERN = "backup filename pattern"
REASON_FILE_SCREENSHOT_PATTERN = "screenshot filename pattern"
REASON_FILE_MEDIA_EXTENSION = "media file extension"
REASON_FILE_NOT_FOUND = "path not found"
LOCAL_PICK_MIN_TOKEN_LENGTH = 3
LOCAL_PICK_NAME_BONUS = 3
LOCAL_PICK_MIN_SCORE = 2
LOCAL_PICK_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "for",
        "and",
        "or",
        "to",
        "of",
        "in",
        "on",
        "is",
        "it",
        "this",
        "that",
        "with",
        "from",
    }
)
# judge-turn (completion-gate Stop judgment). Thresholds are policy, tuned on
# ~/.agents/hooks/tests/fixtures/turn-judge/eval-set.json. A missed deferral
# stalls an unattended session for hours; a false block costs one extra turn
# (the gate caps rejections per session, and stop_hook_active stops loops), so
# the deferred gate leans hard toward blocking. A turn blocks as deferred when
# it ends on a handoff AND either it offers work it could do now OR it leaves
# a failure it could investigate. No "needs the user" answer can veto that: a
# genuine question only shapes the block message. The handoff gate sits at
# 0.75: every deferral scored >= 0.88, while finished turns that merely
# mention a later step scored 0.61-0.67. Doable work sits at 0.50 and
# investigation at 0.60; past the handoff gate no finished turn reached
# either (highest 0.23 and 0.08). Unproven claims
# need a high bar: false completion-claim blocks were the old gate's worst noise.
TURN_JUDGE_REQUEST_TIMEOUT_SECONDS = 5.0
TURN_HANDOFF_THRESHOLD = 0.75
TURN_DOABLE_WORK_THRESHOLD = 0.50
TURN_UNINVESTIGATED_THRESHOLD = 0.60
TURN_CLAIMS_COMPLETION_THRESHOLD = 0.50
TURN_UNPROVEN_CLAIM_THRESHOLD = 0.80
# Second deferred path (2026-09-24): `final_message` can mention leftover doable
# work without ever framing it as a handoff ("It's a ~10-minute add."), so the
# handoff-anchored branch above misses it. This branch fires independently: any
# turn that leaves doable work unstarted, unless that work is already running in
# the background where ending the turn loses nothing. Measured on the 43-item
# eval set plus the 2 real misses and the "needs user comes last" miss (17
# should-be-deferred items): 15/17 caught, 2 finished turns (F292, B38) newly
# false-blocked, legit-wait recall unchanged at 7/10.
TURN_LEAVES_DOABLE_WORK_THRESHOLD = 0.75
TURN_REMAINING_WORK_RUNNING_THRESHOLD = 0.50
# Outcome gating (2026-09-30): `turn_outcome` was asked but never read. Replayed
# over 2,605 logged turns, a confident "waits on the user" (>= 0.85) cleared all
# 6 deferred blocks, and a confident "hands off doable work" newly catches 9
# allowed turns. A waiting turn still blocks on an explicit doable-work offer.
TURN_OUTCOME_CONFIDENT_THRESHOLD = 0.85
TURN_WAITING_TURN_DOABLE_BAR = 0.85
# prework_before_handoff, calibrated live on 43 logged confident-wait turns: scores
# ran 0.39-0.82 (none reached 0.85). At 0.80 it fires on 5, all prep-able
# (a binary-layout choice with no recommendation, "design questions or
# defaults", "is this file synthetic?" answerable from git, "which project uses
# evo?" answerable from the repo); "give me the SSH host" scored 0.49 and passes.
TURN_PREWORK_THRESHOLD = 0.80
# asks_permission_already_given, calibrated live 2026-09-30 (small sample): the 5 real
# "reply push" stops of session 18fa3bd1, after "Go ahead ... have a worker set up the
# repo", scored 0.48-0.65 (4 of 5 at 0.58+); 17 logged waits that truly need the user
# topped out at 0.45. The hook also requires a citable user message, so a false
# flag without a matching grant lets the turn through.
TURN_ALREADY_AUTHORIZED_THRESHOLD = 0.55
# user_withheld_action / closing_asks_user_preference, added 2026-10-09: a 62-case
# hand-labeled counterfactual eval showed a veto on the deferred block lifts held-out
# accuracy 20/25 -> 25/25. Session f66a64b6 (kitty) took five false blocks on turns
# where the user said "don't make changes yet" or the closing question was a taste
# question. A replay of 29 real historical blocks flips 2 (1 of them ambiguous).
# Both bars were fixed before the run.
TURN_USER_WITHHELD_THRESHOLD = 0.50
TURN_CLOSING_PREFERENCE_THRESHOLD = 0.70
