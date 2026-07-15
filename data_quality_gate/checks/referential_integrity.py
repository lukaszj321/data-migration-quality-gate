"""Validate logical parent-child references inside each database."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from data_quality_gate.checks.base import CheckContext, quote_identifier, timed_result
from data_quality_gate.exceptions import CheckExecutionError
from data_quality_gate.models import CheckResult, CheckStatus

CHECK_NAME = "referential_integrity"


def run(context: CheckContext) -> CheckResult:
    started = perf_counter()
    if context.table_config is None:
        raise CheckExecutionError("referential_integrity requires table configuration.")

    references = sorted(
        (column_name, column.references)
        for column_name, column in context.table_config.columns.items()
        if column.references
    )
    try:
        discrepancy_count, samples = _collect_orphans(context, references)
    except SQLAlchemyError as exc:
        raise CheckExecutionError("Failed to execute referential_integrity.") from exc

    status = CheckStatus.PASS if discrepancy_count == 0 else CheckStatus.FAIL
    message = (
        "All configured logical references are valid."
        if status == CheckStatus.PASS
        else f"Found {discrepancy_count} orphaned logical references."
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


def _collect_orphans(
    context: CheckContext, references: list[tuple[str, Any]]
) -> tuple[int, list[dict[str, Any]]]:
    total = 0
    samples: list[dict[str, Any]] = []
    for database, engine in (
        ("source", context.source_engine),
        ("target", context.target_engine),
    ):
        for column, reference in references:
            count = _count_orphans(engine, context.table, column, reference.table, reference.column)
            total += count
            remaining = context.sample_limit - len(samples)
            if count and remaining > 0:
                samples.extend(
                    _sample_orphans(
                        engine,
                        database,
                        context.table,
                        context.primary_key,
                        column,
                        reference.table,
                        reference.column,
                        remaining,
                    )
                )
    return total, samples


def _count_orphans(
    engine: Engine,
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str,
) -> int:
    child = "child_records"
    parent = "parent_records"
    sql = text(
        f"""
        SELECT COUNT(*)
        FROM {quote_identifier(child_table)} AS {child}
        WHERE {child}.{quote_identifier(child_column)} IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM {quote_identifier(parent_table)} AS {parent}
              WHERE {parent}.{quote_identifier(parent_column)}
                    = {child}.{quote_identifier(child_column)}
          )
        """
    )
    with engine.connect() as connection:
        return int(connection.execute(sql).scalar_one())


def _sample_orphans(
    engine: Engine,
    database: str,
    child_table: str,
    primary_key: str,
    child_column: str,
    parent_table: str,
    parent_column: str,
    limit: int,
) -> list[dict[str, Any]]:
    child = "child_records"
    parent = "parent_records"
    sql = text(
        f"""
        SELECT
            {child}.row_id,
            {child}.{quote_identifier(primary_key)} AS primary_key,
            {child}.{quote_identifier(child_column)} AS invalid_value
        FROM {quote_identifier(child_table)} AS {child}
        WHERE {child}.{quote_identifier(child_column)} IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM {quote_identifier(parent_table)} AS {parent}
              WHERE {parent}.{quote_identifier(parent_column)}
                    = {child}.{quote_identifier(child_column)}
          )
        ORDER BY
            {child}.{quote_identifier(child_column)},
            {child}.{quote_identifier(primary_key)} IS NULL,
            {child}.{quote_identifier(primary_key)},
            {child}.row_id
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
            "column": child_column,
            "value": row["invalid_value"],
            "referenced_table": parent_table,
            "referenced_column": parent_column,
        }
        for row in rows
    ]
