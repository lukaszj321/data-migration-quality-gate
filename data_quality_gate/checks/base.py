"""Shared helpers for SQL-based checks."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.engine import Row
from sqlalchemy.exc import SQLAlchemyError

from data_quality_gate.exceptions import CheckExecutionError
from data_quality_gate.models import CheckResult, CheckStatus


@dataclass(frozen=True)
class CheckContext:
    source_engine: Engine
    target_engine: Engine
    table: str
    primary_key: str
    sample_limit: int
    table_config: Any | None = None
    all_tables: dict[str, Any] | None = None


def quote_identifier(identifier: str) -> str:
    return f'"{identifier}"'


def timed_result(
    *,
    check_name: str,
    table: str,
    status: CheckStatus,
    discrepancy_count: int,
    message: str,
    sample_records: list[dict[str, Any]],
    started: float,
) -> CheckResult:
    duration_ms = max(0, round((perf_counter() - started) * 1000))
    return CheckResult(
        check_name=check_name,
        table=table,
        status=status,
        discrepancy_count=discrepancy_count,
        message=message,
        sample_records=sample_records,
        duration_ms=duration_ms,
    )


def execute_scalar_count(engine: Engine, sql: str) -> int:
    try:
        with engine.connect() as connection:
            value = connection.execute(text(sql)).scalar_one()
    except SQLAlchemyError as exc:
        raise CheckExecutionError("Failed to execute count query.") from exc
    return int(value)


def sorted_unique_key_rows(engine: Engine, table: str, primary_key: str) -> Iterator[Row[Any]]:
    quoted_table = quote_identifier(table)
    quoted_key = quote_identifier(primary_key)
    sql = text(
        f"""
        SELECT {quoted_key} AS key_value
        FROM {quoted_table}
        WHERE {quoted_key} IS NOT NULL
        GROUP BY {quoted_key}
        ORDER BY {quoted_key}
        """
    )
    with engine.connect() as connection:
        result = connection.execution_options(stream_results=True).execute(sql)
        yield from result
