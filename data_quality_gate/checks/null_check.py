"""Detect forbidden NULL values in configured columns."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from data_quality_gate.checks.base import CheckContext, quote_identifier, timed_result
from data_quality_gate.exceptions import CheckExecutionError
from data_quality_gate.models import CheckResult, CheckStatus

CHECK_NAME = "null_check"


def run(context: CheckContext) -> CheckResult:
    started = perf_counter()
    if context.table_config is None:
        raise CheckExecutionError("null_check requires table configuration.")

    not_null_columns = sorted(
        column_name
        for column_name, column in context.table_config.columns.items()
        if column.not_null
    )
    try:
        discrepancy_count, samples = _collect_null_violations(context, not_null_columns)
    except SQLAlchemyError as exc:
        raise CheckExecutionError("Failed to execute null_check.") from exc

    status = CheckStatus.PASS if discrepancy_count == 0 else CheckStatus.FAIL
    message = (
        "No forbidden NULL values were found."
        if status == CheckStatus.PASS
        else f"Found {discrepancy_count} forbidden NULL values."
    )
    return timed_result(
        check_name=CHECK_NAME,
        table=context.table,
        status=status,
        discrepancy_count=discrepancy_count,
        message=message,
        sample_records=samples,
        started=started,
    )


def _collect_null_violations(
    context: CheckContext, columns: list[str]
) -> tuple[int, list[dict[str, Any]]]:
    total = 0
    samples: list[dict[str, Any]] = []
    for database, engine in (
        ("source", context.source_engine),
        ("target", context.target_engine),
    ):
        for column in columns:
            count = _count_nulls(engine, context.table, column)
            total += count
            remaining = context.sample_limit - len(samples)
            if count and remaining > 0:
                samples.extend(
                    _sample_nulls(
                        engine,
                        database,
                        context.table,
                        context.primary_key,
                        column,
                        remaining,
                    )
                )
    return total, samples


def _count_nulls(engine: Engine, table: str, column: str) -> int:
    sql = text(
        f"SELECT COUNT(*) FROM {quote_identifier(table)} WHERE {quote_identifier(column)} IS NULL"
    )
    with engine.connect() as connection:
        return int(connection.execute(sql).scalar_one())


def _sample_nulls(
    engine: Engine,
    database: str,
    table: str,
    primary_key: str,
    column: str,
    limit: int,
) -> list[dict[str, Any]]:
    quoted_table = quote_identifier(table)
    quoted_key = quote_identifier(primary_key)
    quoted_column = quote_identifier(column)
    sql = text(
        f"""
        SELECT row_id, {quoted_key} AS primary_key
        FROM {quoted_table}
        WHERE {quoted_column} IS NULL
        ORDER BY {quoted_key} IS NULL, {quoted_key}, row_id
        LIMIT :limit
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(sql, {"limit": limit}).mappings().all()
    return [
        {
            "database": database,
            "primary_key": row["primary_key"],
            "row_id": int(row["row_id"]),
            "column": column,
            "value": None,
        }
        for row in rows
    ]
