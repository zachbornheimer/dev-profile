"""Pure selection logic for ssh-session-reap.py: which pids in a process
table are this session's leftover ssh clients.

Ported line-for-line from the awk script in ssh-session-reap.sh.
"""

from __future__ import annotations

from dataclasses import dataclass

ANCESTOR_WALK_DEFAULT = 16
SSH_CLIENT_NAMES = frozenset({"ssh", "ssh-mini"})
SSHD_NAME = "sshd"
TUNNEL_MARKERS = ("ControlMaster", "ControlPath")


@dataclass(frozen=True, slots=True)
class ProcessEntry:
    ppid: str
    command: str


def parse_table(table: str) -> dict[str, ProcessEntry]:
    """pid -> ProcessEntry, for every line with at least pid, ppid, command."""
    entries: dict[str, ProcessEntry] = {}
    for line in table.splitlines():
        tokens = line.split()
        if len(tokens) < 3:
            continue
        pid, ppid = tokens[0], tokens[1]
        command = " ".join(tokens[2:])
        entries[pid] = ProcessEntry(ppid=ppid, command=command)
    return entries


def _basename(word: str) -> str:
    return word.rsplit("/", 1)[-1]


def _is_ssh_client(command: str) -> bool:
    first_word = command.split()[0] if command.split() else ""
    name = _basename(first_word)
    if name == SSHD_NAME:
        return False
    return name in SSH_CLIENT_NAMES


def _is_tunnel(command: str) -> bool:
    words = command.split()
    if "-N" in words:
        return True
    return any(marker in command for marker in TUNNEL_MARKERS)


def _is_tagged(pid: str, session_id: str, entries: dict[str, ProcessEntry], max_walk: int) -> bool:
    seen: set[str] = set()
    current = pid
    for _ in range(max_walk):
        if not current or current == "0" or current in seen:
            return False
        seen.add(current)
        entry = entries.get(current)
        if entry is None:
            return False
        if session_id in entry.command:
            return True
        current = entry.ppid
    return False


def select_reap_targets(
    table: str,
    session_id: str,
    self_pids: frozenset[str],
    max_walk: int = ANCESTOR_WALK_DEFAULT,
) -> list[str]:
    """Pids of this session's leftover ssh clients, in table order."""
    entries = parse_table(table)
    targets: list[str] = []
    for pid, entry in entries.items():
        if pid in self_pids:
            continue
        if not _is_ssh_client(entry.command):
            continue
        if _is_tunnel(entry.command):
            continue
        if _is_tagged(pid, session_id, entries, max_walk):
            targets.append(pid)
    return targets
