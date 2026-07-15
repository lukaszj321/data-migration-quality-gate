"""JSON report writing and CLI summary formatting."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from data_quality_gate.exceptions import ReportWriteError
from data_quality_gate.models import MigrationReport


def write_json_report(report: MigrationReport, reports_dir: str | Path = "reports") -> Path:
    directory = Path(reports_dir)
    safe_name = safe_report_name(report.summary.migration_name)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    report_path = directory / f"{safe_name}-{timestamp}.json"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        payload = report.model_dump(mode="json")
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ReportWriteError(f"Cannot write JSON report to '{report_path}'.") from exc
    return report_path


def safe_report_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip().lower()).strip("-")
    return safe or "migration"


def format_summary(report: MigrationReport, report_path: Path) -> str:
    summary = report.summary
    return "\n".join(
        [
            f"Migration: {summary.migration_name}",
            f"Status: {summary.status.value}",
            "",
            f"Checks: {summary.checks_total}",
            f"Passed: {summary.checks_passed}",
            f"Warnings: {summary.checks_warned}",
            f"Failed: {summary.checks_failed}",
            "",
            f"Deployment decision: {summary.deployment_decision.value}",
            f"JSON report: {report_path}",
        ]
    )
