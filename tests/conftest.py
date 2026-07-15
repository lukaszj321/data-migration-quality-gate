from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text


@pytest.fixture()
def valid_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "migration.yaml"
    path.write_text(
        """
migration:
  name: test-migration
  source: source_db
  target: target_db
  sample_limit: 2
tables:
  customers:
    primary_key: customer_id
    checks:
      - row_count
      - missing_keys
      - unexpected_keys
      - duplicate_keys
""".strip(),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def sqlite_pair() -> Iterator[tuple[Engine, Engine]]:
    source = create_engine("sqlite+pysqlite:///:memory:", future=True)
    target = create_engine("sqlite+pysqlite:///:memory:", future=True)
    for engine in (source, target):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE items (
                        row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_id VARCHAR(32),
                        payload VARCHAR(120)
                    )
                    """
                )
            )
    yield source, target
    source.dispose()
    target.dispose()


@pytest.fixture()
def postgres_pair() -> Iterator[tuple[Engine, Engine]]:
    source_url = os.getenv("DQG_SOURCE_DB_URL")
    target_url = os.getenv("DQG_TARGET_DB_URL")
    if not source_url or not target_url:
        pytest.skip("DQG_SOURCE_DB_URL and DQG_TARGET_DB_URL are required for integration tests.")

    source = create_engine(source_url, future=True)
    target = create_engine(target_url, future=True)
    try:
        yield source, target
    finally:
        source.dispose()
        target.dispose()
