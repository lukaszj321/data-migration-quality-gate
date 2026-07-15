"""Detect duplicate logical keys in each database."""

from __future__ import annotations

from time import perf_counter

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from data_quality_gate.checks.base import CheckContext, quote_identifier, timed_result
from data_quality_gate.exceptions import CheckExecutionError
from data_quality_gate.models import CheckResult, CheckStatus

CHECK_NAME = "duplicate_keys"


def run(context: CheckContext) -> CheckResult:
    started = perf_counter()
    try:
        source_count, source_samples = _duplicate_groups(
            context.source_engine,
            "source",
            context.table,
            context.primary_key,
            context.sample_limit,
        )
        target_count, target_samples = _duplicate_groups(
            context.target_engine,
            "target",
            context.table,
            context.primary_key,
            context.sample_limit,
        )
    except SQLAlchemyError as exc:
        raise CheckExecutionError("Failed to detect duplicate keys.") from exc

    discrepancy_count = source_count + target_count
    status = CheckStatus.PASS if discrepancy_count == 0 else CheckStatus.FAIL
    message = (
        "No duplicate logical keys were found."
        if status == CheckStatus.PASS
        else f"Found duplicate keys: source={source_count}, target={target_count}."
    )
    samples = (source_samples + target_samples)[: context.sample_limit]
    return timed_result(
        check_name=CHECK_NAME,
        table=context.table,
        status=status,
        discrepancy_count=discrepancy_count,
        message=message,
        sample_records=samples,
        started=started,
    )


def _duplicate_groups(
    engine: Engine, database: str, table: str, primary_key: str, sample_limit: int
) -> tuple[int, list[dict[str, object]]]:
    quoted_table = quote_identifier(table)
    quoted_key = quote_identifier(primary_key)
    count_sql = text(
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT {quoted_key}
            FROM {quoted_table}
            WHERE {quoted_key} IS NOT NULL
            GROUP BY {quoted_key}
            HAVING COUNT(*) > 1
        ) AS duplicate_groups
        """
    )
    sample_sql = text(
        f"""
        SELECT {quoted_key} AS key_value, COUNT(*) AS duplicate_count
        FROM {quoted_table}
        WHERE {quoted_key} IS NOT NULL
        GROUP BY {quoted_key}
        HAVING COUNT(*) > 1
        ORDER BY {quoted_key}
        LIMIT :limit
        """
    )
    with engine.connect() as connection:
        count = int(connection.execute(count_sql).scalar_one())
        rows = connection.execute(sample_sql, {"limit": sample_limit}).mappings().all()

    samples = [
        {
            "database": database,
            primary_key: str(row["key_value"]),
            "duplicate_count": int(row["duplicate_count"]),
        }
        for row in rows
    ]
    return count, samples
