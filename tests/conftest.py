from __future__ import annotations

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
