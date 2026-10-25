"""Decide which Agent of Empires entry a Gas City session needs. Pure: no I/O.

A Gas City session runs in Gas City's own tmux server, so AoE never sees it.
The fix is an AoE terminal entry whose command is `gc session attach <target>`.
This module turns the session's environment and AoE's current entries into
one plan: add the entry, start the existing one, or nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePath

SCOPE_ENV = "GC_AOE_ATTACH"
SCOPE_NAMED = (
    "named"  # sessions with an alias (mayor, brainstormer); pool workers churn
)
SCOPE_ALL = "all"
SCOPE_OFF = "off"
DEFAULT_SCOPE = SCOPE_NAMED

# AoE custom agents (see ~/.agent-of-empires/config.toml [session.custom_agents]),
# one per harness so AoE reads each session's status the way that harness shows it.
AOE_TOOL_BY_PROVIDER = {"claude": "gc-claude", "codex": "gc-codex", "grok": "gc-grok"}


class Action(Enum):
    ADD = "add"
    START = "start"


@dataclass(frozen=True, slots=True)
class GasCitySession:
    city: str
    session_id: str
    alias: str
    provider: str

    @property
    def attach_target(self) -> str:
        return self.alias or self.session_id

    @property
    def title(self) -> str:
        return f"{PurePath(self.city).name}/{self.attach_target}"


@dataclass(frozen=True, slots=True)
class AoeEntry:
    entry_id: str
    title: str


@dataclass(frozen=True, slots=True)
class AttachPlan:
    action: Action
    title: str
    city: str
    tool: str
    extra_args: str
    entry_id: str = ""


def session_from_env(env: Mapping[str, str]) -> GasCitySession | None:
    """The Gas City session this process runs in, or None outside Gas City."""
    city = env.get("GC_CITY", "")
    session_id = env.get("GC_SESSION_ID", "")
    if not city or not session_id:
        return None
    return GasCitySession(
        city=city,
        session_id=session_id,
        alias=env.get("GC_ALIAS", ""),
        provider=env.get("GC_PROVIDER", ""),
    )


def in_scope(session: GasCitySession, scope: str) -> bool:
    if scope == SCOPE_OFF:
        return False
    if scope == SCOPE_ALL:
        return True
    return bool(session.alias)


def plan_attach(
    session: GasCitySession, scope: str, entries: Sequence[AoeEntry]
) -> AttachPlan | None:
    """Add the AoE entry when missing, start it when present; None when out of scope."""
    tool = AOE_TOOL_BY_PROVIDER.get(session.provider)
    if tool is None or not in_scope(session, scope):
        return None
    extra_args = f"--city {session.city} session attach {session.attach_target}"
    existing = next((e for e in entries if e.title == session.title), None)
    if existing is None:
        return AttachPlan(Action.ADD, session.title, session.city, tool, extra_args)
    return AttachPlan(
        Action.START, session.title, session.city, tool, extra_args, existing.entry_id
    )
