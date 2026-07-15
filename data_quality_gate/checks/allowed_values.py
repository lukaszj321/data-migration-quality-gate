"""Validate configured finite value sets."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from sqlalchemy import Engine, bindparam, text
from sqlalchemy.exc import SQLAlchemyError

from data_quality_gate.checks.base import CheckContext, quote_identifier, timed_result
from data_quality_gate.exceptions import CheckExecutionError
from data_quality_gate.models import CheckResult, CheckStatus

CHECK_NAME = "allowed_values"


def run(context: CheckContext) -> CheckResult:
    started = perf_counter()
    if context.table_config is None:
        raise CheckExecutionError("allowed_values requires table configuration.")

    configured_columns = sorted(
        (column_name, column.allowed_values)
        for column_name, column in context.table_config.columns.items()
        if column.allowed_values
    )
    try:
        discrepancy_count, samples = _collect_invalid_values(context, configured_columns)
    except SQLAlchemyError as exc:
        raise CheckExecutionError("Failed to execute allowed_values.") from exc

    status = CheckStatus.PASS if discrepancy_count == 0 else CheckStatus.FAIL
    message = (
        "All configured values are allowed."
        if status == CheckStatus.PASS
        else f"Found {discrepancy_count} values outside configured allow lists."
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


def _collect_invalid_values(
    context: CheckContext, columns: list[tuple[str, list[str] | None]]
) -> tuple[int, list[dict[str, Any]]]:
    total = 0
    samples: list[dict[str, Any]] = []
    for database, engine in (
        ("source", context.source_engine),
        ("target", context.target_engine),
    ):
        for column, allowed_values in columns:
            allowed = list(allowed_values or [])
            count = _count_invalid_values(engine, context.table, column, allowed)
            total += count
            remaining = context.sample_limit - len(samples)
            if count and remaining > 0:
                samples.extend(
                    _sample_invalid_values(
                        engine,
                        database,
                        context.table,
                        context.primary_key,
                        column,
                        allowed,
                        remaining,
                    )
                )
    return total, samples


def _count_invalid_values(
    engine: Engine, table: str, column: str, allowed_values: list[str]
) -> int:
    sql = text(
        f"""
        SELECT COUNT(*)
        FROM {quote_identifier(table)}
        WHERE {quote_identifier(column)} IS NOT NULL
          AND {quote_identifier(column)} NOT IN :allowed_values
        """
    ).bindparams(bindparam("allowed_values", expanding=True))
    with engine.connect() as connection:
        return int(connection.execute(sql, {"allowed_values": allowed_values}).scalar_one())


def _sample_invalid_values(
    engine: Engine,
    database: str,
    table: str,
    primary_key: str,
    column: str,
    allowed_values: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    quoted_table = quote_identifier(table)
    quoted_key = quote_identifier(primary_key)
    quoted_column = quote_identifier(column)
    sql = text(
        f"""
        SELECT row_id, {quoted_key} AS primary_key, {quoted_column} AS invalid_value
        FROM {quoted_table}
        WHERE {quoted_column} IS NOT NULL
          AND {quoted_column} NOT IN :allowed_values
        ORDER BY {quoted_column}, {quoted_key} IS NULL, {quoted_key}, row_id
        LIMIT :limit
        """
    ).bindparams(bindparam("allowed_values", expanding=True))
    with engine.connect() as connection:
        rows = (
            connection.execute(sql, {"allowed_values": allowed_values, "limit": limit})
            .mappings()
            .all()
        )
    return [
        {
            "database": database,
            "primary_key": row["primary_key"],
            "row_id": int(row["row_id"]),
            "column": column,
            "value": row["invalid_value"],
        }
        for row in rows
    ]
