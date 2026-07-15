from __future__ import annotations

from pathlib import Path

import pytest

from data_quality_gate.config import load_config
from data_quality_gate.exceptions import ConfigurationError


def test_loads_valid_configuration(valid_yaml: Path) -> None:
    config = load_config(valid_yaml)

    assert config.migration.name == "test-migration"
    assert config.migration.sample_limit == 2
    assert config.tables["customers"].primary_key == "customer_id"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            """
migration:
  source: source_db
  target: target_db
tables:
  customers:
    primary_key: customer_id
    checks: [row_count]
""",
            "migration.name",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  customers:
    primary_key: customer_id
    checks: [schema_match]
""",
            "schema_match",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
  sample_limit: 0
tables:
  customers:
    primary_key: customer_id
    checks: [row_count]
""",
            "sample_limit",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: source_db
tables:
  customers:
    primary_key: customer_id
    checks: [row_count]
""",
            "different aliases",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  customers:
    primary_key: customer_id
    checks: [row_count, row_count]
""",
            "duplicate checks",
        ),
    ],
)
def test_rejects_invalid_configuration(tmp_path: Path, body: str, expected: str) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(body.strip(), encoding="utf-8")

    with pytest.raises(ConfigurationError) as exc_info:
        load_config(path)

    assert expected in str(exc_info.value)


def test_rejects_empty_tables(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
migration:
  name: test
  source: source_db
  target: target_db
tables: {}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError) as exc_info:
        load_config(path)

    assert "tables" in str(exc_info.value)
