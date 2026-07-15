"""Compare exact configured column values for comparable rows."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from data_quality_gate.checks.base import CheckContext, timed_result
from data_quality_gate.checks.comparison_utils import (
    ComparableRows,
    ComparisonScope,
    comparable_row_pairs,
    duplicate_key_values,
    sample_value,
    unique_rows,
)
from data_quality_gate.exceptions import CheckExecutionError
from data_quality_gate.models import CheckResult, CheckStatus

CHECK_NAME = "column_comparison"


def run(context: CheckContext) -> CheckResult:
    started = perf_counter()
    if context.table_config is None:
        raise CheckExecutionError("column_comparison requires table configuration.")

    columns = sorted(
        column_name
        for column_name, column in context.table_config.columns.items()
        if column.compare and column.tolerance is None
    )
    try:
        discrepancy_count, samples, scope = _compare_columns(context, columns)
    except SQLAlchemyError as exc:
        raise CheckExecutionError("Failed to execute column_comparison.") from exc

    status = CheckStatus.PASS if discrepancy_count == 0 else CheckStatus.FAIL
    message = (
        "All comparable exact values match."
        if status == CheckStatus.PASS
        else f"Found {discrepancy_count} exact value differences."
    )
    message = (
        f"{message} Comparable keys={scope.comparable_keys}; "
        f"skipped missing={scope.missing_keys_skipped}, "
        f"unexpected={scope.unexpected_keys_skipped}, "
        f"duplicate_source={scope.duplicate_keys_source}, "
        f"duplicate_target={scope.duplicate_keys_target}."
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


def _compare_columns(
    context: CheckContext, columns: list[str]
) -> tuple[int, list[dict[str, Any]], ComparisonScope]:
    duplicate_source_keys = duplicate_key_values(
        context.source_engine, context.table, context.primary_key
    )
    duplicate_target_keys = duplicate_key_values(
        context.target_engine, context.table, context.primary_key
    )
    excluded_keys = duplicate_source_keys | duplicate_target_keys
    source_rows = unique_rows(
        context.source_engine, context.table, context.primary_key, columns, excluded_keys
    )
    target_rows = unique_rows(
        context.target_engine, context.table, context.primary_key, columns, excluded_keys
    )
    discrepancy_count = 0
    comparable_keys = 0
    missing_skipped = 0
    unexpected_skipped = 0
    samples: list[dict[str, Any]] = []

    for item in comparable_row_pairs(source_rows, target_rows):
        if isinstance(item, tuple):
            if item[0] == "source_only":
                missing_skipped += 1
            else:
                unexpected_skipped += 1
            continue
        comparable_keys += 1
        for column in columns:
            source_value = item.source[column]
            target_value = item.target[column]
            if source_value == target_value:
                continue
            discrepancy_count += 1
            if len(samples) < context.sample_limit:
                samples.append(_sample(item, column, source_value, target_value))

    scope = ComparisonScope(
        duplicate_keys_source=len(duplicate_source_keys),
        duplicate_keys_target=len(duplicate_target_keys),
        missing_keys_skipped=missing_skipped,
        unexpected_keys_skipped=unexpected_skipped,
        comparable_keys=comparable_keys,
    )
    return discrepancy_count, samples, scope


def _sample(
    rows: ComparableRows, column: str, source_value: Any, target_value: Any
) -> dict[str, Any]:
    return {
        "primary_key": sample_value(rows.source["primary_key"]),
        "column": column,
        "source_value": sample_value(source_value),
        "target_value": sample_value(target_value),
    }
