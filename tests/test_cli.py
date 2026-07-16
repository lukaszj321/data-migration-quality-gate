from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from data_quality_gate import cli
from data_quality_gate.exceptions import (
    ConfigurationError,
    DatabaseConnectionError,
    ReportWriteError,
)
from data_quality_gate.models import (
    CheckResult,
    CheckStatus,
    DeploymentDecision,
    MigrationReport,
    MigrationSummary,
)
from data_quality_gate.reporting import ReportPaths


def test_validate_returns_zero_for_valid_config(valid_yaml: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    assert cli.main(["validate", str(valid_yaml)]) == cli.EXIT_PASS
    assert "Configuration is valid" in capsys.readouterr().out


def test_version_returns_project_version(capsys) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])

    assert exc_info.value.code == cli.EXIT_PASS
    assert "data-quality-gate 0.1.1" in capsys.readouterr().out


def test_validate_returns_invalid_config_for_bad_config(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "bad.yaml"
    path.write_text("migration: {}\ntables: {}\n", encoding="utf-8")

    assert cli.main(["validate", str(path)]) == cli.EXIT_INVALID_CONFIG
    assert "Configuration error" in capsys.readouterr().err


def test_validate_returns_invalid_config_for_missing_file(capsys) -> None:  # type: ignore[no-untyped-def]
    assert cli.main(["validate", "missing.yaml"]) == cli.EXIT_INVALID_CONFIG

    captured = capsys.readouterr()
    assert "Configuration error" in captured.err
    assert "Traceback" not in captured.err


def test_validate_redacts_secret_from_controlled_configuration_error(
    monkeypatch, valid_yaml: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda path: (_ for _ in ()).throw(ConfigurationError("password=super-secret-password")),
    )

    assert cli.main(["validate", str(valid_yaml)]) == cli.EXIT_INVALID_CONFIG

    captured = capsys.readouterr()
    assert "super-secret-password" not in captured.err
    assert "[REDACTED]" in captured.err


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    [
        (CheckStatus.PASS, cli.EXIT_PASS),
        (CheckStatus.WARN, cli.EXIT_WARN),
        (CheckStatus.FAIL, cli.EXIT_FAIL),
    ],
)
def test_run_maps_status_to_exit_code_and_prints_report_paths(
    monkeypatch, valid_yaml: Path, tmp_path: Path, capsys, status: CheckStatus, expected_exit: int
) -> None:  # type: ignore[no-untyped-def]
    report = _report(status)
    paths = ReportPaths(tmp_path / "report.json", tmp_path / "report.html")
    monkeypatch.setattr(cli, "run_quality_gate", lambda config: report)
    monkeypatch.setattr(cli, "write_reports", lambda generated: paths)

    assert cli.main(["run", str(valid_yaml)]) == expected_exit

    captured = capsys.readouterr()
    assert f"Status: {status.value}" in captured.out
    assert f"JSON report: {paths.json_path}" in captured.out
    assert f"HTML report: {paths.html_path}" in captured.out
    assert "postgresql+psycopg://" not in captured.out
    assert "password" not in captured.out.lower()


def test_run_returns_technical_failure_for_report_write_error_without_traceback(
    monkeypatch, valid_yaml: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(cli, "run_quality_gate", lambda config: _report(CheckStatus.PASS))
    monkeypatch.setattr(
        cli,
        "write_reports",
        lambda generated: (_ for _ in ()).throw(
            ReportWriteError("Cannot write HTML report to 'reports/safe.html'.")
        ),
    )

    assert cli.main(["run", str(valid_yaml)]) == cli.EXIT_TECHNICAL_FAILURE

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Technical failure: Cannot write HTML report" in captured.err
    assert "Traceback" not in captured.err
    assert "postgresql+psycopg://" not in captured.err


def test_run_redacts_secret_from_controlled_database_error(
    monkeypatch, valid_yaml: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        cli,
        "run_quality_gate",
        lambda config: (_ for _ in ()).throw(
            DatabaseConnectionError(
                "Cannot connect to "
                "postgresql+psycopg://demo_user:super-secret-password@localhost/db"
            )
        ),
    )

    assert cli.main(["run", str(valid_yaml)]) == cli.EXIT_TECHNICAL_FAILURE

    captured = capsys.readouterr()
    assert "super-secret-password" not in captured.err
    assert "[REDACTED]" in captured.err
    assert "Traceback" not in captured.err


def test_run_returns_technical_failure_for_unavailable_database(
    monkeypatch, valid_yaml: Path, capsys
) -> None:  # type: ignore[no-untyped-def]
    def fail(config) -> None:  # type: ignore[no-untyped-def]
        engine = create_engine("sqlite+pysqlite:///Z:/path/that/does/not/exist/db.sqlite")
        try:
            with engine.connect():
                pass
        except Exception as exc:
            raise DatabaseConnectionError("Cannot connect to database alias 'source_db'.") from exc
        finally:
            engine.dispose()

    monkeypatch.setattr(cli, "run_quality_gate", fail)

    assert cli.main(["run", str(valid_yaml)]) == cli.EXIT_TECHNICAL_FAILURE

    captured = capsys.readouterr()
    assert "Cannot connect to database alias" in captured.err
    assert "Traceback" not in captured.err


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
        deployment_decision=_decision(status),
        checks_total=1,
        checks_passed=1 if status == CheckStatus.PASS else 0,
        checks_warned=1 if status == CheckStatus.WARN else 0,
        checks_failed=1 if status == CheckStatus.FAIL else 0,
        started_at=started,
        finished_at=started,
        duration_ms=0,
    )
    failed_checks = [result] if status == CheckStatus.FAIL else []
    return MigrationReport(summary=summary, failed_checks=failed_checks, results=[result])


def _decision(status: CheckStatus) -> DeploymentDecision:
    if status == CheckStatus.PASS:
        return DeploymentDecision.ALLOW
    if status == CheckStatus.WARN:
        return DeploymentDecision.REVIEW
    return DeploymentDecision.BLOCK
