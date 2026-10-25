"""TypeSafe key resolution and HTTP adapter."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from constants import (
    API_KEY_ENV,
    BASE_URL_ENV,
    BASE_URLS,
    KEYCHAIN_SERVICE,
    KEYCHAIN_TIMEOUT_SECONDS,
    MODEL_BY_BASE_URL,
    OPENROUTER_API_KEY_ENV,
    OPENROUTER_BASE_URL,
    OPENROUTER_KEYCHAIN_SERVICE,
    REASON_MISSING_KEY,
    REASON_TIMEOUT,
    REASON_UNAVAILABLE,
    REQUEST_TIMEOUT_SECONDS,
    SYSTEMONE_PATH,
)

Getenv = Callable[..., str | None]
Urlopen = Callable[..., Any]
ReadKeychain = Callable[[], str | None]
Adapt = Callable[[str, dict[str, Any]], dict[str, Any]]


class JudgmentError(Exception):
    """TypeSafe request failed; callers fail open.

    ``hops`` names every base URL that failed, set only when more than one did, because
    ``reason`` is the last hop's and would otherwise hide why the first one failed.
    """

    def __init__(self, reason: str, hops: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.hops = hops


def resolve_api_key(
    getenv: Getenv,
    read_keychain: ReadKeychain,
) -> str | None:
    env_key = getenv(API_KEY_ENV)
    if env_key is not None and env_key.strip():
        return env_key.strip()
    secret = read_keychain()
    if secret is None:
        return None
    stripped = secret.strip()
    return stripped or None


def read_generic_password(account: str, service: str) -> str | None:
    try:
        completed = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                account,
                "-s",
                service,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=KEYCHAIN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    secret = completed.stdout.rstrip("\n")
    return secret or None


def write_generic_password(account: str, service: str, secret: str) -> None:
    try:
        completed = subprocess.run(
            [
                "security",
                "add-generic-password",
                "-a",
                account,
                "-s",
                service,
                "-w",
                secret,
                "-U",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=KEYCHAIN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("failed to write typesafe-api-key to keychain") from exc
    if completed.returncode != 0:
        raise RuntimeError("failed to write typesafe-api-key to keychain")


def default_read_keychain(getenv: Getenv) -> str | None:
    account = getenv("USER") or ""
    if not account:
        return None
    return read_generic_password(account, KEYCHAIN_SERVICE)


def _systemone_url(base: str) -> str:
    base = base.strip().rstrip("/")
    return base if base.endswith(SYSTEMONE_PATH) else f"{base}{SYSTEMONE_PATH}"


def fallback_chain(getenv: Getenv) -> tuple[str, ...]:
    """Base URLs to try in order, starting at TYPESAFE_BASE_URL when it names one."""
    start = (getenv(BASE_URL_ENV) or "").strip().rstrip("/")
    if not start:
        return BASE_URLS
    if start in BASE_URLS:
        return BASE_URLS[BASE_URLS.index(start) :]
    return (start, *BASE_URLS)


def _post(
    payload: dict[str, Any],
    base: str,
    api_key: str,
    urlopen: Urlopen | None,
) -> dict[str, Any]:
    opener = urlopen if urlopen is not None else urllib.request.urlopen
    request = urllib.request.Request(
        _systemone_url(base),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        exc.read()
        raise JudgmentError(f"http {exc.code}") from exc
    except TimeoutError as exc:
        raise JudgmentError(REASON_TIMEOUT) from exc
    except urllib.error.URLError as exc:
        raise JudgmentError(_url_reason(exc)) from exc
    except OSError as exc:
        raise JudgmentError(REASON_UNAVAILABLE) from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JudgmentError(REASON_UNAVAILABLE) from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("answers"), dict):
        raise JudgmentError(REASON_UNAVAILABLE)
    return parsed


def _hops(failures: list[tuple[str, str]]) -> str:
    if len(failures) < 2:
        return ""
    return " > ".join(f"{urlparse(base).hostname} {reason}" for base, reason in failures)


def hop_key(base: str, api_key: str, getenv: Getenv) -> str | None:
    """The key a base URL accepts: OpenRouter takes its own (None when absent, so the hop is skipped)."""
    if base != OPENROUTER_BASE_URL:
        return api_key
    env_key = (getenv(OPENROUTER_API_KEY_ENV) or "").strip()
    if env_key:
        return env_key
    account = getenv("USER") or ""
    return read_generic_password(account, OPENROUTER_KEYCHAIN_SERVICE) if account else None


def ask(
    payload: dict[str, Any],
    api_key: str,
    *,
    getenv: Getenv = os.getenv,
    urlopen: Urlopen | None = None,
    adapt: Adapt | None = None,
) -> dict[str, Any]:
    """POST to each base URL in turn; the last failure propagates (callers fail open).

    ``adapt`` reshapes the payload for a base URL whose limits differ.
    """
    failures: list[tuple[str, str]] = []
    for base in fallback_chain(getenv):
        key = hop_key(base, api_key, getenv)
        if key is None:
            continue
        shaped = adapt(base, payload) if adapt is not None else payload
        model = MODEL_BY_BASE_URL.get(base, shaped.get("model"))
        try:
            return _post({**shaped, "model": model}, base, key, urlopen)
        except JudgmentError as exc:
            failures.append((base, exc.reason))
    raise JudgmentError(failures[-1][1] if failures else REASON_MISSING_KEY, hops=_hops(failures))


def _url_reason(exc: urllib.error.URLError) -> str:
    cause = exc.reason
    if isinstance(cause, TimeoutError):
        return REASON_TIMEOUT
    text = str(cause).lower()
    if "timed out" in text or "timeout" in text:
        return REASON_TIMEOUT
    return REASON_UNAVAILABLE


def missing_key_error() -> JudgmentError:
    return JudgmentError(REASON_MISSING_KEY)
