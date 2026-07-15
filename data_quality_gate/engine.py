"""Quality gate orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy import Engine

from data_quality_gate.checks import duplicate_keys, missing_keys, row_count, unexpected_keys
from data_quality_gate.checks.base import CheckContext
from data_quality_gate.config import CheckName, QualityGateConfig
from data_quality_gate.database import build_engine, verify_connection
from data_quality_gate.exceptions import CheckExecutionError
from data_quality_gate.models import (
    CheckResult,
    CheckStatus,
    DeploymentDecision,
    MigrationReport,
    MigrationSummary,
)

CheckFunction = Callable[[CheckContext], CheckResult]

CHECK_REGISTRY: dict[CheckName, CheckFunction] = {
    CheckName.ROW_COUNT: row_count.run,
    CheckName.MISSING_KEYS: missing_keys.run,
    CheckName.UNEXPECTED_KEYS: unexpected_keys.run,
    CheckName.DUPLICATE_KEYS: duplicate_keys.run,
}


def run_quality_gate(config: QualityGateConfig) -> MigrationReport:
    source_engine = build_engine(config.migration.source)
    target_engine = build_engine(config.migration.target)
    verify_connection(source_engine, config.migration.source)
    verify_connection(target_engine, config.migration.target)
    return run_checks(config, source_engine, target_engine)


def run_checks(
    config: QualityGateConfig, source_engine: Engine, target_engine: Engine
) -> MigrationReport:
    started_at = datetime.now(UTC)
    started = perf_counter()
    results: list[CheckResult] = []

    for table_name in sorted(config.tables):
        table_config = config.tables[table_name]
        for check_name in table_config.checks:
            check = CHECK_REGISTRY.get(check_name)
            if check is None:
                raise CheckExecutionError(f"Unsupported check '{check_name}'.")
            context = CheckContext(
                source_engine=source_engine,
                target_engine=target_engine,
                table=table_name,
                primary_key=table_config.primary_key,
                sample_limit=config.migration.sample_limit,
            )
            results.append(check(context))

    finished_at = datetime.now(UTC)
    status = aggregate_status(results)
    summary = MigrationSummary(
        migration_name=config.migration.name,
        status=status,
        deployment_decision=deployment_decision_for(status),
        checks_total=len(results),
        checks_passed=sum(result.status == CheckStatus.PASS for result in results),
        checks_warned=sum(result.status == CheckStatus.WARN for result in results),
        checks_failed=sum(result.status == CheckStatus.FAIL for result in results),
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=max(0, round((perf_counter() - started) * 1000)),
    )
    failed_checks = [result for result in results if result.status == CheckStatus.FAIL]
    return MigrationReport(summary=summary, failed_checks=failed_checks, results=results)


def aggregate_status(results: list[CheckResult]) -> CheckStatus:
    if any(result.status == CheckStatus.FAIL for result in results):
        return CheckStatus.FAIL
    if any(result.status == CheckStatus.WARN for result in results):
        return CheckStatus.WARN
    return CheckStatus.PASS


def deployment_decision_for(status: CheckStatus) -> DeploymentDecision:
    if status == CheckStatus.FAIL:
        return DeploymentDecision.BLOCK
    if status == CheckStatus.WARN:
        return DeploymentDecision.REVIEW
    return DeploymentDecision.ALLOW
