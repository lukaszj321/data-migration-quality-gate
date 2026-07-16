"""Shared helpers for value comparison checks."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, text

from data_quality_gate.checks.base import quote_identifier


@dataclass(frozen=True)
class ComparableRows:
    source: dict[str, Any]
    target: dict[str, Any]


@dataclass(frozen=True)
class ComparisonScope:
    duplicate_keys_source: int
    duplicate_keys_target: int
    missing_keys_skipped: int
    unexpected_keys_skipped: int
    comparable_keys: int


def duplicate_key_values(engine: Engine, table: str, primary_key: str) -> set[Any]:
    quoted_table = quote_identifier(table)
    quoted_key = quote_identifier(primary_key)
    sql = text(
        f"""
        SELECT {quoted_key} AS primary_key
        FROM {quoted_table}
        WHERE {quoted_key} IS NOT NULL
        GROUP BY {quoted_key}
        HAVING COUNT(*) > 1
        ORDER BY {quoted_key}
        """
    )
    with engine.connect() as connection:
        return {row["primary_key"] for row in connection.execute(sql).mappings()}


def unique_rows(
    engine: Engine,
    table: str,
    primary_key: str,
    columns: list[str],
    excluded_keys: set[Any] | None = None,
) -> Generator[dict[str, Any]]:
    quoted_table = quote_identifier(table)
    quoted_key = quote_identifier(primary_key)
    selected_columns = ",\n            ".join(
        f"records.{quote_identifier(column)} AS {quote_identifier(column)}" for column in columns
    )
    sql = text(
        f"""
        WITH key_counts AS (
            SELECT {quoted_key} AS key_value, COUNT(*) AS key_count
            FROM {quoted_table}
            WHERE {quoted_key} IS NOT NULL
            GROUP BY {quoted_key}
        )
        SELECT
            records.row_id,
            records.{quoted_key} AS primary_key,
            {selected_columns}
        FROM {quoted_table} AS records
        JOIN key_counts
          ON key_counts.key_value = records.{quoted_key}
        WHERE key_counts.key_count = 1
        ORDER BY records.{quoted_key}, records.row_id
        """
    )
    with engine.connect() as connection:
        result = connection.execution_options(stream_results=True).execute(sql).mappings()
        try:
            for row in result:
                if excluded_keys is not None and row["primary_key"] in excluded_keys:
                    continue
                yield dict(row)
        finally:
            result.close()


def comparable_row_pairs(
    source_rows: Iterator[dict[str, Any]],
    target_rows: Iterator[dict[str, Any]],
) -> Iterator[ComparableRows | tuple[str, dict[str, Any]]]:
    source = _next_row(source_rows)
    target = _next_row(target_rows)
    while source is not None or target is not None:
        if source is None and target is not None:
            yield ("target_only", target)
            target = _next_row(target_rows)
            continue
        if target is None and source is not None:
            yield ("source_only", source)
            source = _next_row(source_rows)
            continue
        if source is None or target is None:
            continue
        source_key = source["primary_key"]
        target_key = target["primary_key"]
        if source_key == target_key:
            yield ComparableRows(source=source, target=target)
            source = _next_row(source_rows)
            target = _next_row(target_rows)
        elif source_key < target_key:
            yield ("source_only", source)
            source = _next_row(source_rows)
        else:
            yield ("target_only", target)
            target = _next_row(target_rows)


def sample_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def canonical_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": str(value)}
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": format(value, "f")}
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"type": "date", "value": value.isoformat()}
    return {"type": type(value).__name__, "value": str(value)}


def _next_row(rows: Iterator[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        return next(rows)
    except StopIteration:
        return None
