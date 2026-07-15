from __future__ import annotations

import json
from datetime import UTC, datetime

from data_quality_gate.models import (
    CheckResult,
    CheckStatus,
    DeploymentDecision,
    MigrationReport,
    MigrationSummary,
)
from data_quality_gate.reporting import safe_report_name, write_json_report


def make_report() -> MigrationReport:
    started = datetime(2024, 1, 1, tzinfo=UTC)
    result = CheckResult(
        check_name="row_count",
        table="customers",
        status=CheckStatus.PASS,
        discrepancy_count=0,
        message="Row counts match.",
        sample_records=[{"source_count": 1, "target_count": 1, "difference": 0}],
        duration_ms=1,
    )
    summary = MigrationSummary(
        migration_name="Legacy Payments",
        status=CheckStatus.PASS,
        deployment_decision=DeploymentDecision.ALLOW,
        checks_total=1,
        checks_passed=1,
        checks_warned=0,
        checks_failed=0,
        started_at=started,
        finished_at=started,
        duration_ms=1,
    )
    return MigrationReport(summary=summary, failed_checks=[], results=[result])


def test_safe_report_name() -> None:
    assert safe_report_name("Legacy Payments!") == "legacy-payments"


def test_write_json_report_serializes_model(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = write_json_report(make_report(), tmp_path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "0.1"
    assert payload["summary"]["deployment_decision"] == "ALLOW"
    assert payload["results"][0]["sample_records"][0]["source_count"] == 1
