"""Detect keys present in target but absent in source."""

from __future__ import annotations

from collections.abc import Iterator
from time import perf_counter
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from data_quality_gate.checks.base import CheckContext, sorted_unique_key_rows, timed_result
from data_quality_gate.checks.comparison_utils import sample_value
from data_quality_gate.exceptions import CheckExecutionError
from data_quality_gate.models import CheckResult, CheckStatus

CHECK_NAME = "unexpected_keys"


def run(context: CheckContext) -> CheckResult:
    started = perf_counter()
    try:
        discrepancy_count, samples = _target_only_keys(context)
    except SQLAlchemyError as exc:
        raise CheckExecutionError("Failed to compare unexpected keys.") from exc

    status = CheckStatus.PASS if discrepancy_count == 0 else CheckStatus.WARN
    message = (
        "No target-only keys were found."
        if status == CheckStatus.PASS
        else f"Found {discrepancy_count} target-only keys."
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


def _target_only_keys(context: CheckContext) -> tuple[int, list[dict[str, Any]]]:
    source_rows = sorted_unique_key_rows(context.source_engine, context.table, context.primary_key)
    target_rows = sorted_unique_key_rows(context.target_engine, context.table, context.primary_key)
    count = 0
    samples: list[dict[str, Any]] = []

    try:
        source_value = _next_key(source_rows)
        target_value = _next_key(target_rows)

        while target_value is not None:
            if source_value is None or target_value < source_value:
                count += 1
                if len(samples) < context.sample_limit:
                    samples.append({context.primary_key: sample_value(target_value)})
                target_value = _next_key(target_rows)
            elif source_value == target_value:
                source_value = _next_key(source_rows)
                target_value = _next_key(target_rows)
            else:
                source_value = _next_key(source_rows)
    finally:
        source_rows.close()
        target_rows.close()

    return count, samples


def _next_key(rows: Iterator[Any]) -> Any | None:
    try:
        row = next(rows)
    except StopIteration:
        return None
    return row.key_value
