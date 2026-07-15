"""Row count comparison."""

from __future__ import annotations

from time import perf_counter

from data_quality_gate.checks.base import (
    CheckContext,
    execute_scalar_count,
    quote_identifier,
    timed_result,
)
from data_quality_gate.models import CheckResult, CheckStatus

CHECK_NAME = "row_count"


def run(context: CheckContext) -> CheckResult:
    started = perf_counter()
    table = quote_identifier(context.table)
    source_count = execute_scalar_count(context.source_engine, f"SELECT COUNT(*) FROM {table}")
    target_count = execute_scalar_count(context.target_engine, f"SELECT COUNT(*) FROM {table}")
    difference = target_count - source_count
    status = CheckStatus.PASS if source_count == target_count else CheckStatus.FAIL
    message = (
        f"Row counts match at {source_count}."
        if status == CheckStatus.PASS
        else (
            "Row count mismatch: "
            f"source={source_count}, target={target_count}, difference={difference}."
        )
    )
    return timed_result(
        check_name=CHECK_NAME,
        table=context.table,
        status=status,
        discrepancy_count=abs(difference),
        message=message,
        sample_records=[
            {
                "source_count": source_count,
                "target_count": target_count,
                "difference": difference,
            }
        ],
        started=started,
    )
