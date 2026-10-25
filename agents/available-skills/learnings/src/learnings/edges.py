"""Injectable system edges; no credentials, redirects, proxies, or hosted fallback."""

import json
import re
from collections.abc import Callable
from pathlib import Path
from time import monotonic
from typing import Protocol

import httpx

BASE_URL = "http://localhost:11434"
PATHS = frozenset({"/v1/systemone", "/v1/chat/completions"})
SECRET = re.compile(r"(?i)(?:bearer\s+\S+|(?:api[_-]?key|password|secret|token)\s*[:=]\s*[^\s,}]+)")


def sanitized(text: str) -> str:
    return SECRET.sub("[REDACTED]", text)


class Transport(Protocol):
    async def post(self, path: str, payload: dict[str, object]) -> object: ...


class LocalTransport:
    def __init__(self, client: httpx.AsyncClient, timeout: float) -> None:
        if timeout <= 0:
            raise ValueError("local transport timeout must be positive")
        self.client = client
        self.timeout = timeout

    async def post(self, path: str, payload: dict[str, object]) -> object:
        if path not in PATHS:
            raise ValueError(f"local transport refuses path {path}")
        response = await self.client.post(f"{BASE_URL}{path}", json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()


class Files:
    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def write(self, path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(sanitized(json.dumps(data, ensure_ascii=False, indent=2)), encoding="utf-8")
        path.chmod(0o600)

    def locate(self, root: Path, pattern: str) -> list[Path]:
        return sorted(root.glob(pattern))


class Calls:
    def __init__(
        self,
        transport: Transport,
        save: Callable[[str, object], None],
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.transport = transport
        self.save = save
        self.clock = clock
        self.count = 0
        self.records: list[dict[str, object]] = []

    async def request(self, phase: str, path: str, payload: dict[str, object]) -> object:
        self.count += 1
        name = f"{self.count:03d}-{phase}"
        record: dict[str, object] = {"artifact": name, "phase": phase}
        self.records.append(record)
        self.save(f"{name}-request", payload)
        start = self.clock()
        try:
            result = await self.transport.post(path, payload)
        except (httpx.HTTPError, ValueError) as exc:
            record.update(error=type(exc).__name__, seconds=self.clock() - start)
            self.save(f"{name}-failure", {"error": record["error"], "seconds": record["seconds"]})
            raise
        record["seconds"] = self.clock() - start
        self.save(
            f"{name}-response",
            {
                "raw": result,
                "seconds": record["seconds"],
                "input_chars": len(json.dumps(payload)),
            },
        )
        return result
