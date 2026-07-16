"""Report artifact writing and CLI summary formatting."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from data_quality_gate.exceptions import ReportWriteError
from data_quality_gate.html_reporting import render_html_report
from data_quality_gate.models import MigrationReport

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


@dataclass(frozen=True)
class ReportPaths:
    json_path: Path
    html_path: Path


def write_reports(
    report: MigrationReport,
    reports_dir: str | Path = "reports",
    *,
    now: datetime | None = None,
) -> ReportPaths:
    paths = create_report_paths(report, reports_dir, now=now)
    write_json_report_to_path(report, paths.json_path)
    write_html_report_to_path(report, paths.html_path)
    return paths


def write_json_report(
    report: MigrationReport,
    reports_dir: str | Path = "reports",
    *,
    now: datetime | None = None,
) -> Path:
    path = create_report_paths(report, reports_dir, now=now).json_path
    write_json_report_to_path(report, path)
    return path


def create_report_paths(
    report: MigrationReport,
    reports_dir: str | Path = "reports",
    *,
    now: datetime | None = None,
) -> ReportPaths:
    directory = Path(reports_dir)
    base_name = report_base_name(report.summary.migration_name, now=now)
    return ReportPaths(
        json_path=directory / f"{base_name}.json",
        html_path=directory / f"{base_name}.html",
    )


def report_base_name(name: str, *, now: datetime | None = None) -> str:
    timestamp = report_timestamp(now)
    return f"{safe_report_name(name)}-{timestamp}"


def report_timestamp(now: datetime | None = None) -> str:
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def write_json_report_to_path(report: MigrationReport, report_path: Path) -> None:
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        payload = report.model_dump(mode="json")
        with report_path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    except OSError as exc:
        raise ReportWriteError(f"Cannot write JSON report to '{report_path}'.") from exc


def write_html_report_to_path(report: MigrationReport, report_path: Path) -> None:
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("x", encoding="utf-8") as handle:
            handle.write(render_html_report(report))
    except OSError as exc:
        raise ReportWriteError(f"Cannot write HTML report to '{report_path}'.") from exc


def safe_report_name(name: str) -> str:
    without_controls = "".join(character for character in name if character >= " ")
    normalized = unicodedata.normalize("NFKD", without_controls)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_name.strip().lower()
    without_paths = lowered.replace("/", "-").replace("\\", "-")
    safe = re.sub(r"[^a-z0-9._-]+", "-", without_paths)
    safe = re.sub(r"\.+", ".", safe)
    safe = re.sub(r"-+", "-", safe)
    safe = safe.strip(" ._-")
    safe = safe.replace("..", ".")
    if not safe:
        safe = "migration"
    reserved_check = safe.split(".", 1)[0].upper()
    if reserved_check in WINDOWS_RESERVED_NAMES:
        safe = f"{reserved_check.lower()}-migration"
    return safe


def format_summary(report: MigrationReport, paths: ReportPaths) -> str:
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
            f"JSON report: {paths.json_path}",
            f"HTML report: {paths.html_path}",
        ]
    )
