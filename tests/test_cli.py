from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from data_quality_gate import cli
from data_quality_gate.models import (
    CheckResult,
    CheckStatus,
    DeploymentDecision,
    MigrationReport,
    MigrationSummary,
)


def test_validate_returns_zero_for_valid_config(valid_yaml: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert cli.main(["validate", str(valid_yaml)]) == cli.EXIT_PASS
    assert "Configuration is valid" in capsys.readouterr().out


def test_validate_returns_invalid_config_for_bad_config(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "bad.yaml"
    path.write_text("migration: {}\ntables: {}\n", encoding="utf-8")

    assert cli.main(["validate", str(path)]) == cli.EXIT_INVALID_CONFIG
    assert "Configuration error" in capsys.readouterr().err


def test_run_maps_status_to_exit_code(monkeypatch, valid_yaml: Path, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    report = _report(CheckStatus.WARN)
    monkeypatch.setattr(cli, "run_quality_gate", lambda config: report)
    monkeypatch.setattr(cli, "write_json_report", lambda generated: tmp_path / "report.json")

    assert cli.main(["run", str(valid_yaml)]) == cli.EXIT_WARN


def test_exit_code_for_status() -> None:
    assert cli.exit_code_for_status(CheckStatus.PASS) == 0
    assert cli.exit_code_for_status(CheckStatus.WARN) == 1
    assert cli.exit_code_for_status(CheckStatus.FAIL) == 2


def _report(status: CheckStatus) -> MigrationReport:
    started = datetime(2024, 1, 1, tzinfo=UTC)
    result = CheckResult(
        check_name="unexpected_keys",
        table="customers",
        status=status,
        discrepancy_count=1 if status != CheckStatus.PASS else 0,
        message="message",
        sample_records=[],
        duration_ms=0,
    )
    summary = MigrationSummary(
        migration_name="test-migration",
        status=status,
        deployment_decision=DeploymentDecision.REVIEW,
        checks_total=1,
        checks_passed=0,
        checks_warned=1,
        checks_failed=0,
        started_at=started,
        finished_at=started,
        duration_ms=0,
    )
    return MigrationReport(summary=summary, failed_checks=[], results=[result])
