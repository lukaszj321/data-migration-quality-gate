"""Safety helpers for user-facing diagnostics."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SECRET_REPLACEMENT = "[REDACTED]"
SECRET_QUERY_KEYS = ("password", "passwd", "pwd", "secret", "token", "key")
URL_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s'\"<>]+")


def redact_secrets(value: object) -> str:
    text = str(value)
    text = URL_PATTERN.sub(lambda match: _redact_url(match.group(0)), text)
    text = _redact_known_environment_values(text)
    text = re.sub(
        r"(?i)(password|passwd|pwd|secret|token|key)=([^&\s'\"<>]+)",
        rf"\1={SECRET_REPLACEMENT}",
        text,
    )
    return text


def safe_error_message(error: BaseException) -> str:
    return redact_secrets(error)


def _redact_url(raw_url: str) -> str:
    try:
        parts = urlsplit(raw_url)
    except ValueError:
        return SECRET_REPLACEMENT

    netloc = parts.netloc
    if "@" in netloc:
        userinfo, hostinfo = netloc.rsplit("@", 1)
        username = userinfo.split(":", 1)[0]
        netloc = f"{username}:{SECRET_REPLACEMENT}@{hostinfo}" if username else hostinfo

    query = _redact_query(parts.query)
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def _redact_query(query: str) -> str:
    if not query:
        return query
    redacted_pairs = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        if _is_secret_key(key):
            redacted_pairs.append((key, SECRET_REPLACEMENT))
        else:
            redacted_pairs.append((key, value))
    return urlencode(redacted_pairs)


def _redact_known_environment_values(text: str) -> str:
    for secret in _environment_secret_values():
        if secret and secret in text:
            text = text.replace(secret, SECRET_REPLACEMENT)
    return text


def _environment_secret_values() -> Iterable[str]:
    for key, value in os.environ.items():
        if _is_secret_key(key) and value:
            yield value


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SECRET_QUERY_KEYS)
