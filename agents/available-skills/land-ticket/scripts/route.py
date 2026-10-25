"""Map a Linear identifier to workspace and MCP. No network."""

from __future__ import annotations

import re
from dataclasses import dataclass

IDENTIFIER = re.compile(r"^([A-Za-z][A-Za-z0-9]*)-(\d+)$")

WORKSPACE_PERSONAL = "personal"
WORKSPACE_WORK = "work"
MCP_PERSONAL = "linear-personal"
MCP_WORK = "linear-sah"
PREFIX_PERSONAL = "ZYS"
PREFIX_WORK = "SAH"


@dataclass(frozen=True, slots=True)
class Route:
    workspace: str
    mcp: str


ROUTES_BY_PREFIX: dict[str, Route] = {
    PREFIX_PERSONAL: Route(workspace=WORKSPACE_PERSONAL, mcp=MCP_PERSONAL),
    PREFIX_WORK: Route(workspace=WORKSPACE_WORK, mcp=MCP_WORK),
}


class InvalidIdentifierError(ValueError):
    """Raised when the value is not TEAM-123."""

    def __init__(self, identifier: str) -> None:
        super().__init__(
            f"not a Linear identifier (TEAM-123): {identifier!r}"
        )
        self.identifier = identifier


class UnknownPrefixError(ValueError):
    """Raised when the prefix is not a known Linear workspace."""

    def __init__(self, identifier: str, prefix: str) -> None:
        known = ", ".join(sorted(ROUTES_BY_PREFIX))
        super().__init__(
            f"unknown Linear prefix {prefix!r} on {identifier!r}; "
            f"known prefixes: {known}"
        )
        self.identifier = identifier
        self.prefix = prefix


def route_for(identifier: str) -> Route:
    match = IDENTIFIER.match(identifier)
    if match is None:
        raise InvalidIdentifierError(identifier)
    prefix = match.group(1).upper()
    routed = ROUTES_BY_PREFIX.get(prefix)
    if routed is None:
        raise UnknownPrefixError(identifier, prefix)
    return routed


def workspace_for(identifier: str) -> str:
    return route_for(identifier).workspace


def mcp_server_for(identifier: str) -> str:
    return route_for(identifier).mcp
