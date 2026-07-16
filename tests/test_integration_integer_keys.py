from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from data_quality_gate.checks import (
    column_comparison,
    missing_keys,
    numeric_tolerance,
    unexpected_keys,
)
from data_quality_gate.checks.base import CheckContext
from data_quality_gate.config import CheckName, ColumnConfig, TableConfig
from data_quality_gate.models import CheckStatus

pytestmark = pytest.mark.integration


def test_integer_keys_match_without_false_missing_or_unexpected(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_integer_key_table(source, target, "integer_keys_identical")
    rows = [(1, "one", "1.00"), (2, "two", "2.00"), (10, "ten", "10.00"), (11, "eleven", "11.00")]
    _insert_integer_rows(source, "integer_keys_identical", rows)
    _insert_integer_rows(target, "integer_keys_identical", rows)

    context = _integer_context(source, target, "integer_keys_identical")

    missing = missing_keys.run(context)
    unexpected = unexpected_keys.run(context)
    exact = column_comparison.run(context)
    numeric = numeric_tolerance.run(context)

    assert missing.status == CheckStatus.PASS
    assert missing.discrepancy_count == 0
    assert unexpected.status == CheckStatus.PASS
    assert unexpected.discrepancy_count == 0
    assert exact.status == CheckStatus.PASS
    assert "Comparable keys=4" in exact.message
    assert "skipped missing=0, unexpected=0" in exact.message
    assert numeric.status == CheckStatus.PASS
    assert "Comparable keys=4" in numeric.message
    assert "skipped missing=0, unexpected=0" in numeric.message


def test_integer_keys_report_missing_key_without_mispairing(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_integer_key_table(source, target, "integer_keys_missing")
    _insert_integer_rows(
        source,
        "integer_keys_missing",
        [(1, "one", "1.00"), (2, "two", "2.00"), (10, "ten", "10.00"), (11, "eleven", "11.00")],
    )
    _insert_integer_rows(
        target,
        "integer_keys_missing",
        [(1, "one", "1.00"), (10, "ten", "10.00"), (11, "eleven", "11.00")],
    )

    context = _integer_context(source, target, "integer_keys_missing")

    missing = missing_keys.run(context)
    unexpected = unexpected_keys.run(context)
    exact = column_comparison.run(context)
    numeric = numeric_tolerance.run(context)

    assert missing.status == CheckStatus.FAIL
    assert missing.discrepancy_count == 1
    assert missing.sample_records == [{"record_id": 2}]
    assert unexpected.status == CheckStatus.PASS
    assert unexpected.discrepancy_count == 0
    assert exact.status == CheckStatus.PASS
    assert "Comparable keys=3" in exact.message
    assert "skipped missing=1, unexpected=0" in exact.message
    assert numeric.status == CheckStatus.PASS
    assert "Comparable keys=3" in numeric.message
    assert "skipped missing=1, unexpected=0" in numeric.message


def test_integer_keys_report_unexpected_key_without_mispairing(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_integer_key_table(source, target, "integer_keys_unexpected")
    _insert_integer_rows(
        source,
        "integer_keys_unexpected",
        [(1, "one", "1.00"), (2, "two", "2.00"), (10, "ten", "10.00"), (11, "eleven", "11.00")],
    )
    _insert_integer_rows(
        target,
        "integer_keys_unexpected",
        [
            (1, "one", "1.00"),
            (2, "two", "2.00"),
            (3, "three", "3.00"),
            (10, "ten", "10.00"),
            (11, "eleven", "11.00"),
        ],
    )

    context = _integer_context(source, target, "integer_keys_unexpected")

    missing = missing_keys.run(context)
    unexpected = unexpected_keys.run(context)
    exact = column_comparison.run(context)
    numeric = numeric_tolerance.run(context)

    assert missing.status == CheckStatus.PASS
    assert missing.discrepancy_count == 0
    assert unexpected.status == CheckStatus.WARN
    assert unexpected.discrepancy_count == 1
    assert unexpected.sample_records == [{"record_id": 3}]
    assert exact.status == CheckStatus.PASS
    assert "Comparable keys=4" in exact.message
    assert "skipped missing=0, unexpected=1" in exact.message
    assert numeric.status == CheckStatus.PASS
    assert "Comparable keys=4" in numeric.message
    assert "skipped missing=0, unexpected=1" in numeric.message


def test_integer_keys_assign_value_differences_to_correct_records(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_integer_key_table(source, target, "integer_keys_differences")
    _insert_integer_rows(
        source,
        "integer_keys_differences",
        [(1, "one", "1.00"), (2, "two", "2.00"), (10, "ten", "10.00"), (11, "eleven", "11.00")],
    )
    _insert_integer_rows(
        target,
        "integer_keys_differences",
        [
            (1, "one", "1.00"),
            (2, "two", "2.00"),
            (10, "TEN_CHANGED", "10.00"),
            (11, "eleven", "11.50"),
        ],
    )

    context = _integer_context(source, target, "integer_keys_differences")

    exact = column_comparison.run(context)
    numeric = numeric_tolerance.run(context)

    assert exact.status == CheckStatus.FAIL
    assert exact.discrepancy_count == 1
    assert exact.sample_records == [
        {
            "primary_key": 10,
            "column": "exact_value",
            "source_value": "ten",
            "target_value": "TEN_CHANGED",
        }
    ]
    assert "Comparable keys=4" in exact.message

    assert numeric.status == CheckStatus.FAIL
    assert numeric.discrepancy_count == 1
    assert numeric.sample_records[0]["primary_key"] == 11
    assert numeric.sample_records[0]["column"] == "numeric_value"
    assert 2 not in [sample["primary_key"] for sample in exact.sample_records]
    assert 2 not in [sample["primary_key"] for sample in numeric.sample_records]
    assert "Comparable keys=4" in numeric.message


def _create_integer_key_table(source: Engine, target: Engine, table: str) -> None:
    sql = f"""
    CREATE TABLE {table} (
        row_id BIGSERIAL PRIMARY KEY,
        record_id INTEGER,
        exact_value TEXT,
        numeric_value NUMERIC(12, 2)
    )
    """
    for engine in (source, target):
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
            connection.execute(text(sql))


def _insert_integer_rows(engine: Engine, table: str, rows: list[tuple[int, str, str]]) -> None:
    with engine.begin() as connection:
        for record_id, exact_value, numeric_value in rows:
            connection.execute(
                text(
                    f"""
                    INSERT INTO {table} (record_id, exact_value, numeric_value)
                    VALUES (:record_id, :exact_value, :numeric_value)
                    """
                ),
                {
                    "record_id": record_id,
                    "exact_value": exact_value,
                    "numeric_value": numeric_value,
                },
            )


def _integer_context(source: Engine, target: Engine, table: str) -> CheckContext:
    table_config = TableConfig(
        primary_key="record_id",
        checks=[
            CheckName.MISSING_KEYS,
            CheckName.UNEXPECTED_KEYS,
            CheckName.COLUMN_COMPARISON,
            CheckName.NUMERIC_TOLERANCE,
        ],
        columns={
            "record_id": ColumnConfig(not_null=True),
            "exact_value": ColumnConfig(compare=True),
            "numeric_value": ColumnConfig(compare=True, tolerance="0.01"),
        },
    )
    return CheckContext(source, target, table, "record_id", 5, table_config, {table: table_config})
