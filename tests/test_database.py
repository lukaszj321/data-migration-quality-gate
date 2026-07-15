from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from data_quality_gate.database import build_engine, connection_url_for_alias, verify_connection
from data_quality_gate.exceptions import DatabaseConnectionError


def test_connection_url_for_alias_reads_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DQG_SOURCE_DB_URL", "sqlite+pysqlite:///:memory:")

    assert connection_url_for_alias("source_db") == "sqlite+pysqlite:///:memory:"


def test_connection_url_for_alias_rejects_unknown_alias() -> None:
    with pytest.raises(DatabaseConnectionError) as exc_info:
        connection_url_for_alias("warehouse")

    assert "Unknown database alias" in str(exc_info.value)


def test_connection_url_for_alias_requires_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("DQG_TARGET_DB_URL", raising=False)

    with pytest.raises(DatabaseConnectionError) as exc_info:
        connection_url_for_alias("target_db")

    assert "DQG_TARGET_DB_URL" in str(exc_info.value)


def test_build_engine_and_verify_connection(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DQG_SOURCE_DB_URL", "sqlite+pysqlite:///:memory:")
    engine = build_engine("source_db")
    try:
        verify_connection(engine, "source_db")
    finally:
        engine.dispose()


def test_verify_connection_wraps_database_error() -> None:
    engine = create_engine("sqlite+pysqlite:///Z:/path/that/does/not/exist/db.sqlite", future=True)
    try:
        with pytest.raises(DatabaseConnectionError):
            verify_connection(engine, "source_db")
    finally:
        engine.dispose()
