from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from data_quality_gate.checks import checksum, column_comparison, numeric_tolerance
from data_quality_gate.checks.base import CheckContext
from data_quality_gate.config import CheckName, ColumnConfig, TableConfig
from data_quality_gate.models import CheckStatus

pytestmark = pytest.mark.integration


def test_column_comparison_passes_for_identical_values_and_different_order(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_compare_table(source, target, "m2b_exact_ok")
    _insert_compare_rows(
        source,
        "m2b_exact_ok",
        [("B", "beta", "2024-01-02T10:00:00Z", "2.00"), ("A", "alpha", None, "1.00")],
    )
    _insert_compare_rows(
        target,
        "m2b_exact_ok",
        [("A", "alpha", None, "1.00"), ("B", "beta", "2024-01-02T10:00:00Z", "2.00")],
    )

    result = column_comparison.run(_exact_context(source, target, "m2b_exact_ok", 5))

    assert result.status == CheckStatus.PASS


def test_column_comparison_detects_text_timestamp_and_null_differences(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_compare_table(source, target, "m2b_exact_bad")
    _insert_compare_rows(
        source,
        "m2b_exact_bad",
        [
            ("A", "alpha", "2024-01-01T10:00:00Z", "1.00"),
            ("B", "same", None, "2.00"),
            ("C", "one", "2024-01-03T10:00:00Z", "3.00"),
        ],
    )
    _insert_compare_rows(
        target,
        "m2b_exact_bad",
        [
            ("A", "ALPHA", "2024-01-01T10:05:00Z", "1.00"),
            ("B", "same", "2024-01-02T10:00:00Z", "2.00"),
            ("C", "two", "2024-01-03T10:00:00Z", "3.00"),
        ],
    )

    result = column_comparison.run(_exact_context(source, target, "m2b_exact_bad", 3))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 4
    assert len(result.sample_records) == 3
    assert result.sample_records[0]["primary_key"] == "A"
    assert result.sample_records[0]["column"] == "occurred_at"


def test_column_comparison_skips_missing_unexpected_and_duplicate_keys(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_compare_table(source, target, "m2b_exact_skip")
    _insert_compare_rows(
        source,
        "m2b_exact_skip",
        [
            ("A", "same", None, "1.00"),
            ("B", "missing", None, "2.00"),
            ("D", "x", None, "4.00"),
            ("D", "y", None, "4.00"),
        ],
    )
    _insert_compare_rows(
        target,
        "m2b_exact_skip",
        [
            ("A", "same", None, "1.00"),
            ("C", "extra", None, "3.00"),
            ("D", "changed", None, "4.00"),
        ],
    )

    result = column_comparison.run(_exact_context(source, target, "m2b_exact_skip", 5))

    assert result.status == CheckStatus.PASS
    assert "skipped missing=1" in result.message
    assert "unexpected=1" in result.message
    assert "duplicate_source=1" in result.message


def test_column_comparison_handles_empty_tables(postgres_pair: tuple[Engine, Engine]) -> None:
    source, target = postgres_pair
    _create_compare_table(source, target, "m2b_exact_empty")

    result = column_comparison.run(_exact_context(source, target, "m2b_exact_empty", 5))

    assert result.status == CheckStatus.PASS


def test_numeric_tolerance_boundaries_negative_precision_and_nulls(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_numeric_table(source, target, "m2b_numeric")
    _insert_numeric_rows(
        source,
        "m2b_numeric",
        [
            ("A", "10.0000", "1.0000"),
            ("B", "10.0000", "1.0000"),
            ("C", "10.0000", "1.0000"),
            ("D", "-5.0000", "1.0000"),
            ("E", "123456789.123456", "1.0000"),
            ("F", None, None),
            ("G", None, "1.0000"),
        ],
    )
    _insert_numeric_rows(
        target,
        "m2b_numeric",
        [
            ("A", "10.0000", "1.0000"),
            ("B", "10.0050", "1.0000"),
            ("C", "10.0100", "1.0000"),
            ("D", "-5.0200", "1.0000"),
            ("E", "123456789.123457", "1.0200"),
            ("F", None, None),
            ("G", "1.0000", "1.0000"),
        ],
    )

    result = numeric_tolerance.run(_numeric_context(source, target, "m2b_numeric", 5))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 3
    assert [sample["primary_key"] for sample in result.sample_records] == ["D", "E", "G"]


def test_numeric_tolerance_skips_uncomparable_and_empty_tables(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_numeric_table(source, target, "m2b_numeric_skip")
    _insert_numeric_rows(
        source,
        "m2b_numeric_skip",
        [
            ("A", "1.00", "1.00"),
            ("B", "2.00", "1.00"),
            ("D", "4.00", "1.00"),
            ("D", "5.00", "1.00"),
        ],
    )
    _insert_numeric_rows(
        target,
        "m2b_numeric_skip",
        [("A", "1.00", "1.00"), ("C", "3.00", "1.00"), ("D", "99.00", "1.00")],
    )

    result = numeric_tolerance.run(_numeric_context(source, target, "m2b_numeric_skip", 5))

    assert result.status == CheckStatus.PASS
    assert "skipped missing=1" in result.message
    assert "duplicate_source=1" in result.message

    _create_numeric_table(source, target, "m2b_numeric_empty")
    empty = numeric_tolerance.run(_numeric_context(source, target, "m2b_numeric_empty", 5))

    assert empty.status == CheckStatus.PASS


def test_checksum_covers_order_values_missing_extra_duplicates_nulls_and_types(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_compare_table(source, target, "m2b_checksum")
    rows = [
        ("B", "a|bc", "2024-01-02T10:00:00Z", "2.00"),
        ("A", "ab|c", "2024-01-01T10:00:00Z", "1.00"),
        ("C", None, None, None),
    ]
    _insert_compare_rows(source, "m2b_checksum", rows)
    _insert_compare_rows(target, "m2b_checksum", list(reversed(rows)))

    first = checksum.run(_checksum_context(source, target, "m2b_checksum"))
    second = checksum.run(_checksum_context(source, target, "m2b_checksum"))

    assert first.status == CheckStatus.PASS
    assert first.sample_records == second.sample_records

    with target.begin() as connection:
        connection.execute(text("UPDATE m2b_checksum SET txt = 'changed' WHERE id = 'A'"))

    changed = checksum.run(_checksum_context(source, target, "m2b_checksum"))

    assert changed.status == CheckStatus.FAIL

    with target.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO m2b_checksum (id, txt, occurred_at, amount)
                VALUES ('A', 'changed', '2024-01-01T10:00:00Z', 1.00)
                """
            )
        )

    duplicated = checksum.run(_checksum_context(source, target, "m2b_checksum"))

    assert duplicated.status == CheckStatus.FAIL


def test_checksum_handles_empty_tables(postgres_pair: tuple[Engine, Engine]) -> None:
    source, target = postgres_pair
    _create_compare_table(source, target, "m2b_checksum_empty")

    result = checksum.run(_checksum_context(source, target, "m2b_checksum_empty"))

    assert result.status == CheckStatus.PASS
    assert result.sample_records[0]["source_row_count"] == 0


def _create_compare_table(source: Engine, target: Engine, table: str) -> None:
    sql = f"""
    CREATE TABLE {table} (
        row_id BIGSERIAL PRIMARY KEY,
        id VARCHAR(32),
        txt VARCHAR(120),
        occurred_at TIMESTAMPTZ,
        amount NUMERIC(20,6)
    )
    """
    for engine in (source, target):
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
            connection.execute(text(sql))


def _create_numeric_table(source: Engine, target: Engine, table: str) -> None:
    sql = f"""
    CREATE TABLE {table} (
        row_id BIGSERIAL PRIMARY KEY,
        id VARCHAR(32),
        amount NUMERIC(20,6),
        fee NUMERIC(20,6)
    )
    """
    for engine in (source, target):
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
            connection.execute(text(sql))


def _insert_compare_rows(
    engine: Engine, table: str, rows: list[tuple[str, str | None, str | None, str | None]]
) -> None:
    with engine.begin() as connection:
        for row_id, txt, occurred_at, amount in rows:
            connection.execute(
                text(
                    f"""
                    INSERT INTO {table} (id, txt, occurred_at, amount)
                    VALUES (:id, :txt, :occurred_at, :amount)
                    """
                ),
                {"id": row_id, "txt": txt, "occurred_at": occurred_at, "amount": amount},
            )


def _insert_numeric_rows(
    engine: Engine, table: str, rows: list[tuple[str, str | None, str | None]]
) -> None:
    with engine.begin() as connection:
        for row_id, amount, fee in rows:
            connection.execute(
                text(
                    f"""
                    INSERT INTO {table} (id, amount, fee)
                    VALUES (:id, :amount, :fee)
                    """
                ),
                {"id": row_id, "amount": amount, "fee": fee},
            )


def _exact_context(source: Engine, target: Engine, table: str, sample_limit: int) -> CheckContext:
    table_config = TableConfig(
        primary_key="id",
        checks=[CheckName.COLUMN_COMPARISON],
        columns={
            "id": ColumnConfig(not_null=True),
            "txt": ColumnConfig(compare=True),
            "occurred_at": ColumnConfig(compare=True),
        },
    )
    return CheckContext(
        source, target, table, "id", sample_limit, table_config, {table: table_config}
    )


def _numeric_context(source: Engine, target: Engine, table: str, sample_limit: int) -> CheckContext:
    table_config = TableConfig(
        primary_key="id",
        checks=[CheckName.NUMERIC_TOLERANCE],
        columns={
            "id": ColumnConfig(not_null=True),
            "amount": ColumnConfig(compare=True, tolerance="0.01"),
            "fee": ColumnConfig(compare=True, tolerance="0.01"),
        },
    )
    return CheckContext(
        source, target, table, "id", sample_limit, table_config, {table: table_config}
    )


def _checksum_context(source: Engine, target: Engine, table: str) -> CheckContext:
    table_config = TableConfig.model_validate(
        {
            "primary_key": "id",
            "checks": [CheckName.CHECKSUM],
            "columns": {
                "id": {},
                "txt": {},
                "occurred_at": {},
                "amount": {},
            },
            "checksum": {"columns": ["id", "txt", "occurred_at", "amount"]},
        }
    )
    return CheckContext(source, target, table, "id", 5, table_config, {table: table_config})
