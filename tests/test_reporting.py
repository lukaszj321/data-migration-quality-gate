from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from data_quality_gate.exceptions import ReportWriteError
from data_quality_gate.models import (
    CheckResult,
    CheckStatus,
    DeploymentDecision,
    MigrationReport,
    MigrationSummary,
)
from data_quality_gate.reporting import (
    create_report_paths,
    report_base_name,
    safe_report_name,
    write_html_report_to_path,
    write_json_report,
    write_json_report_to_path,
    write_reports,
)

FIXED_NOW = datetime(2026, 7, 16, 10, 15, 30, 123456, tzinfo=UTC)


def make_report(name: str = "Legacy Payments") -> MigrationReport:
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
        migration_name=name,
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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Legacy Payments!", "legacy-payments"),
        ("Zażółć płatności 2024", "zazoc-patnosci-2024"),
        ("name with spaces", "name-with-spaces"),
        ("../secret", "secret"),
        ("..\\secret", "secret"),
        ("../../outside", "outside"),
        ("..\\..\\outside", "outside"),
        ("/absolute/path", "absolute-path"),
        ("C:\\absolute\\path", "c-absolute-path"),
        ("a/b\\c", "a-b-c"),
        ("\n\t", "migration"),
        ("...", "migration"),
        ("///", "migration"),
        ("CON", "con-migration"),
        ("CON.txt", "con-migration"),
    ],
)
def test_safe_report_name(raw: str, expected: str) -> None:
    assert safe_report_name(raw) == expected


def test_report_base_name_uses_safe_name_and_utc_timestamp() -> None:
    assert (
        report_base_name("Legacy Payments", now=FIXED_NOW)
        == "legacy-payments-20260716T101530123456Z"
    )


def test_create_report_paths_uses_common_base_name(tmp_path: Path) -> None:
    paths = create_report_paths(make_report(), tmp_path, now=FIXED_NOW)

    assert paths.json_path.parent == tmp_path
    assert paths.html_path.parent == tmp_path
    assert paths.json_path.stem == paths.html_path.stem
    assert paths.json_path.suffix == ".json"
    assert paths.html_path.suffix == ".html"


def test_create_report_paths_stays_under_reports_directory(tmp_path: Path) -> None:
    paths = create_report_paths(make_report("../../outside"), tmp_path, now=FIXED_NOW)

    assert paths.json_path.parent == tmp_path
    assert paths.html_path.parent == tmp_path
    assert ".." not in paths.json_path.name
    assert paths.json_path.resolve().parent == tmp_path.resolve()


def test_write_json_report_serializes_model(tmp_path: Path) -> None:
    path = write_json_report(make_report(), tmp_path, now=FIXED_NOW)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "0.1"
    assert payload["summary"]["deployment_decision"] == "ALLOW"
    assert payload["results"][0]["sample_records"][0]["source_count"] == 1


def test_write_reports_creates_json_and_html_with_same_base(tmp_path: Path) -> None:
    paths = write_reports(make_report(), tmp_path, now=FIXED_NOW)

    assert paths.json_path.exists()
    assert paths.html_path.exists()
    assert paths.json_path.stem == paths.html_path.stem
    assert "<!DOCTYPE html>" in paths.html_path.read_text(encoding="utf-8")


def test_write_reports_creates_reports_directory(tmp_path: Path) -> None:
    reports_dir = tmp_path / "nested" / "reports"

    paths = write_reports(make_report(), reports_dir, now=FIXED_NOW)

    assert paths.json_path.exists()
    assert paths.html_path.exists()


def test_write_reports_does_not_overwrite_existing_json(tmp_path: Path) -> None:
    paths = create_report_paths(make_report(), tmp_path, now=FIXED_NOW)
    paths.json_path.parent.mkdir(parents=True, exist_ok=True)
    paths.json_path.write_text("already here", encoding="utf-8")

    with pytest.raises(ReportWriteError) as exc_info:
        write_reports(make_report(), tmp_path, now=FIXED_NOW)

    assert "Cannot write JSON report" in str(exc_info.value)
    assert paths.json_path.read_text(encoding="utf-8") == "already here"


def test_write_json_report_to_path_wraps_os_errors(tmp_path: Path) -> None:
    with pytest.raises(ReportWriteError) as exc_info:
        write_json_report_to_path(make_report(), tmp_path)

    assert "Cannot write JSON report" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, OSError)


def test_write_html_report_to_path_wraps_os_errors(tmp_path: Path) -> None:
    with pytest.raises(ReportWriteError) as exc_info:
        write_html_report_to_path(make_report(), tmp_path)

    assert "Cannot write HTML report" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, OSError)


def test_write_reports_keeps_json_when_html_write_fails(tmp_path: Path) -> None:
    report = make_report()
    paths = create_report_paths(report, tmp_path, now=FIXED_NOW)
    paths.html_path.mkdir(parents=True)

    with pytest.raises(ReportWriteError) as exc_info:
        write_reports(report, tmp_path, now=FIXED_NOW)

    assert "Cannot write HTML report" in str(exc_info.value)
    assert paths.json_path.exists()
    assert paths.html_path.is_dir()


def test_new_check_result_serializes_without_schema_version_change() -> None:
    result = CheckResult(
        check_name="schema_match",
        table="transactions",
        status=CheckStatus.FAIL,
        discrepancy_count=1,
        message="Found 1 schema difference.",
        sample_records=[
            {
                "column": "description",
                "issue": "length_mismatch",
                "source": "varchar(255)",
                "target": "varchar(80)",
            }
        ],
        duration_ms=3,
    )

    payload = result.model_dump(mode="json")

    assert payload["check_name"] == "schema_match"
    assert payload["sample_records"][0]["issue"] == "length_mismatch"
