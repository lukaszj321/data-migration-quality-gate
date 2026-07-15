"""Compare configured numeric values with Decimal tolerances."""

from __future__ import annotations

from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from data_quality_gate.checks.base import CheckContext, timed_result
from data_quality_gate.checks.comparison_utils import (
    ComparisonScope,
    comparable_row_pairs,
    duplicate_key_values,
    sample_value,
    unique_rows,
)
from data_quality_gate.exceptions import CheckExecutionError
from data_quality_gate.models import CheckResult, CheckStatus

CHECK_NAME = "numeric_tolerance"


def run(context: CheckContext) -> CheckResult:
    started = perf_counter()
    if context.table_config is None:
        raise CheckExecutionError("numeric_tolerance requires table configuration.")

    tolerances = {
        column_name: column.tolerance
        for column_name, column in context.table_config.columns.items()
        if column.tolerance is not None
    }
    columns = sorted(tolerances)
    try:
        discrepancy_count, samples, scope = _compare_numeric(context, columns, tolerances)
    except SQLAlchemyError as exc:
        raise CheckExecutionError("Failed to execute numeric_tolerance.") from exc

    status = CheckStatus.PASS if discrepancy_count == 0 else CheckStatus.FAIL
    message = (
        "All comparable numeric values are within tolerance."
        if status == CheckStatus.PASS
        else f"Found {discrepancy_count} numeric differences outside tolerance."
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


def _compare_numeric(
    context: CheckContext,
    columns: list[str],
    tolerances: dict[str, Decimal | None],
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
            tolerance = tolerances[column]
            if tolerance is None or _within_tolerance(source_value, target_value, tolerance):
                continue
            discrepancy_count += 1
            if len(samples) < context.sample_limit:
                samples.append(
                    _sample(
                        item.source["primary_key"],
                        column,
                        source_value,
                        target_value,
                        tolerance,
                    )
                )

    scope = ComparisonScope(
        duplicate_keys_source=len(duplicate_source_keys),
        duplicate_keys_target=len(duplicate_target_keys),
        missing_keys_skipped=missing_skipped,
        unexpected_keys_skipped=unexpected_skipped,
        comparable_keys=comparable_keys,
    )
    return discrepancy_count, samples, scope


def _within_tolerance(source_value: Any, target_value: Any, tolerance: Decimal) -> bool:
    if source_value is None and target_value is None:
        return True
    if source_value is None or target_value is None:
        return False
    source_decimal = _to_decimal(source_value)
    target_decimal = _to_decimal(target_value)
    return abs(source_decimal - target_decimal) <= tolerance


def _sample(
    primary_key: Any,
    column: str,
    source_value: Any,
    target_value: Any,
    tolerance: Decimal,
) -> dict[str, Any]:
    difference = None
    if source_value is not None and target_value is not None:
        difference = format(abs(_to_decimal(source_value) - _to_decimal(target_value)), "f")
    return {
        "primary_key": sample_value(primary_key),
        "column": column,
        "source_value": sample_value(source_value),
        "target_value": sample_value(target_value),
        "difference": difference,
        "tolerance": format(tolerance, "f"),
    }


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | str):
        return Decimal(str(value))
    return Decimal(str(value))
