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
    checks: [column_comparison]
""",
            "column_comparison",
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


def test_loads_valid_column_configuration(tmp_path: Path) -> None:
    path = tmp_path / "migration.yaml"
    path.write_text(
        """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  customers:
    primary_key: customer_id
    checks: [schema_match, null_check, allowed_values]
    columns:
      customer_id:
        not_null: true
      country_code:
        allowed_values: [PL, DE]
  accounts:
    primary_key: account_id
    checks: [referential_integrity]
    columns:
      account_id:
        not_null: true
      customer_id:
        references:
          table: customers
          column: customer_id
""".strip(),
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.tables["customers"].columns["customer_id"].not_null is True
    assert config.tables["accounts"].columns["customer_id"].references is not None


def test_loads_valid_compare_tolerance_and_checksum_configuration(tmp_path: Path) -> None:
    path = tmp_path / "migration.yaml"
    path.write_text(
        """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  accounts:
    primary_key: account_id
    checks: [column_comparison, numeric_tolerance, checksum]
    columns:
      account_id:
        not_null: true
      account_type:
        compare: true
      balance:
        compare: true
        tolerance: 0.01
    checksum:
      columns: [account_id, account_type, balance]
""".strip(),
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.tables["accounts"].columns["account_type"].compare is True
    assert str(config.tables["accounts"].columns["balance"].tolerance) == "0.01"
    assert config.tables["accounts"].checksum is not None


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  customers:
    primary_key: customer_id
    checks: [allowed_values]
    columns:
      country_code:
        allowed_values: []
""",
            "allowed_values must not be empty",
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
    checks: [allowed_values]
    columns:
      country_code:
        allowed_values: [PL, PL]
""",
            "duplicate allowed values",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  accounts:
    primary_key: account_id
    checks: [referential_integrity]
    columns:
      account_id: {}
      customer_id:
        references:
          table: customers
          column: customer_id
""",
            "unknown table",
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
    columns:
      customer_id: {}
  accounts:
    primary_key: account_id
    checks: [referential_integrity]
    columns:
      account_id: {}
      customer_id:
        references:
          table: customers
          column: missing_id
""",
            "unknown column",
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
    checks: [null_check]
    columns:
      customer_id: {}
""",
            "not_null",
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
    checks: [allowed_values]
    columns:
      customer_id:
        not_null: true
""",
            "allowed_values requires",
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
    checks: [referential_integrity]
    columns:
      customer_id:
        not_null: true
""",
            "referential_integrity requires",
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
            "schema_match requires",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  accounts:
    primary_key: account_id
    checks: [numeric_tolerance]
    columns:
      account_id: {}
      balance:
        compare: true
        tolerance: -0.01
""",
            "tolerance must not be negative",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  accounts:
    primary_key: account_id
    checks: [numeric_tolerance]
    columns:
      account_id: {}
      balance:
        tolerance: 0.01
""",
            "tolerance requires compare",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  accounts:
    primary_key: account_id
    checks: [numeric_tolerance]
    columns:
      account_id: {}
      balance:
        compare: true
""",
            "numeric_tolerance requires",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  accounts:
    primary_key: account_id
    checks: [column_comparison]
    columns:
      account_id: {}
      balance:
        compare: true
        tolerance: 0.01
""",
            "column_comparison requires",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  accounts:
    primary_key: account_id
    checks: [checksum]
    columns:
      account_id: {}
""",
            "checksum requires",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  accounts:
    primary_key: account_id
    checks: [checksum]
    columns:
      account_id: {}
    checksum:
      columns: []
""",
            "checksum.columns",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  accounts:
    primary_key: account_id
    checks: [checksum]
    columns:
      account_id: {}
      account_type: {}
    checksum:
      columns: [account_id, account_id]
""",
            "duplicate checksum columns",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  accounts:
    primary_key: account_id
    checks: [checksum]
    columns:
      account_id: {}
    checksum:
      columns: [account_id, missing_column]
""",
            "unknown configured columns",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  accounts:
    primary_key: missing_id
    checks: [schema_match]
    columns:
      account_id: {}
""",
            "primary_key must be present",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  "accounts;DROP":
    primary_key: account_id
    checks: [row_count]
""",
            "table name",
        ),
        (
            """
migration:
  name: test
  source: source_db
  target: target_db
tables:
  accounts:
    primary_key: account_id
    checks: [schema_match]
    columns:
      "account_id --": {}
""",
            "column name",
        ),
    ],
)
def test_rejects_invalid_column_configuration(tmp_path: Path, body: str, expected: str) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(body.strip(), encoding="utf-8")

    with pytest.raises(ConfigurationError) as exc_info:
        load_config(path)

    assert expected in str(exc_info.value)
