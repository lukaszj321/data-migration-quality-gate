"""Standalone HTML rendering for migration reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from html import escape
from typing import Any

from data_quality_gate import __version__
from data_quality_gate.models import CheckResult, MigrationReport


@dataclass(frozen=True)
class HtmlFragment:
    html: str


def render_html_report(report: MigrationReport) -> str:
    """Render a complete standalone HTML document for a migration report."""

    summary = report.summary
    parts = [
        "<!DOCTYPE html>",
        '<html lang="pl">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape_text(summary.migration_name)} - Data Migration Quality Gate</title>",
        "<style>",
        _css(),
        "</style>",
        "</head>",
        "<body>",
        '<main class="page">',
        _header(report),
        _decision(report),
        _summary_cards(report),
        _failed_checks(report),
        _all_results(report),
        _details(report),
        _metadata(report),
        "</main>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts) + "\n"


def render_value(value: Any) -> str:
    """Render one value as escaped HTML with stable formatting."""

    if value is None:
        return '<span class="null-value">NULL</span>'
    if isinstance(value, bool):
        return escape_text("true" if value else "false")
    if isinstance(value, int):
        return escape_text(str(value))
    if isinstance(value, Decimal):
        return escape_text(format(value, "f"))
    if isinstance(value, datetime):
        return escape_text(value.isoformat())
    if isinstance(value, date):
        return escape_text(value.isoformat())
    if isinstance(value, str):
        return escape_text(value)
    if isinstance(value, list | dict):
        return f"<pre>{escape_text(format_json_value(value))}</pre>"
    return escape_text(format_json_value(value))


def format_json_value(value: Any) -> str:
    normalized = _normalize_json_value(value)
    return json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True)


def escape_text(value: str) -> str:
    return escape(value, quote=True)


def _header(report: MigrationReport) -> str:
    summary = report.summary
    return "\n".join(
        [
            '<section class="panel report-header">',
            "<p>Data Migration Quality Gate</p>",
            f"<h1>{escape_text(summary.migration_name)}</h1>",
            '<dl class="meta-grid">',
            _term("Rozpoczęcie", summary.started_at.isoformat()),
            _term("Zakończenie", summary.finished_at.isoformat()),
            _term("Czas wykonania", f"{summary.duration_ms} ms"),
            _term("Schema version", report.schema_version),
            "</dl>",
            "</section>",
        ]
    )


def _decision(report: MigrationReport) -> str:
    summary = report.summary
    status = summary.status.value
    decision = summary.deployment_decision.value
    return "\n".join(
        [
            f'<section class="decision-panel status-{status.lower()} decision-{decision.lower()}">',
            "<div>",
            "<p>Status migracji</p>",
            f"<strong>{escape_text(status)}</strong>",
            "</div>",
            "<div>",
            "<p>Decyzja wdrożeniowa</p>",
            f"<strong>{escape_text(decision)}</strong>",
            "</div>",
            "</section>",
        ]
    )


def _summary_cards(report: MigrationReport) -> str:
    summary = report.summary
    cards = [
        ("Kontrole razem", summary.checks_total),
        ("PASS", summary.checks_passed),
        ("WARN", summary.checks_warned),
        ("FAIL", summary.checks_failed),
        ("Nieudane kontrole", len(report.failed_checks)),
        ("Czas wykonania", f"{summary.duration_ms} ms"),
    ]
    return "\n".join(
        [
            '<section class="panel">',
            "<h2>Podsumowanie</h2>",
            '<div class="summary-grid">',
            *[
                '<div class="summary-card">'
                f"<span>{escape_text(label)}</span>"
                f"<strong>{escape_text(str(value))}</strong>"
                "</div>"
                for label, value in cards
            ],
            "</div>",
            "</section>",
        ]
    )


def _failed_checks(report: MigrationReport) -> str:
    if not report.failed_checks:
        return "\n".join(
            [
                '<section class="panel">',
                "<h2>Nieudane kontrole</h2>",
                '<p class="empty-state">Brak kontroli ze statusem FAIL.</p>',
                "</section>",
            ]
        )
    rows = [
        [
            result.check_name,
            result.table,
            result.discrepancy_count,
            result.message,
        ]
        for result in report.failed_checks
    ]
    return "\n".join(
        [
            '<section class="panel">',
            "<h2>Nieudane kontrole</h2>",
            _table(["Kontrola", "Tabela", "Niezgodności", "Komunikat"], rows),
            "</section>",
        ]
    )


def _all_results(report: MigrationReport) -> str:
    rows = [
        [
            _status_badge(result.status.value),
            result.check_name,
            result.table,
            result.discrepancy_count,
            result.message,
            f"{result.duration_ms} ms",
        ]
        for result in report.results
    ]
    return "\n".join(
        [
            '<section class="panel">',
            "<h2>Wszystkie wyniki</h2>",
            _table(
                ["Status", "Kontrola", "Tabela", "Niezgodności", "Komunikat", "Czas"],
                rows,
            ),
            "</section>",
        ]
    )


def _details(report: MigrationReport) -> str:
    if not report.results:
        return "\n".join(
            [
                '<section class="panel">',
                "<h2>Szczegóły wyników</h2>",
                '<p class="empty-state">Raport nie zawiera wyników kontroli.</p>',
                "</section>",
            ]
        )
    rendered = [
        '<section class="panel">',
        "<h2>Szczegóły wyników</h2>",
    ]
    for result in report.results:
        rendered.append(_result_detail(result))
    rendered.append("</section>")
    return "\n".join(rendered)


def _result_detail(result: CheckResult) -> str:
    data = result.model_dump(mode="python")
    details = data.get("details")
    sample_records = result.sample_records
    title = (
        f"{result.status.value} - {result.table} - {result.check_name} ({result.discrepancy_count})"
    )
    rendered = [
        "<details>",
        f"<summary>{escape_text(title)}</summary>",
        '<dl class="detail-grid">',
        _term("check_name", result.check_name),
        _term("table", result.table),
        _term("status", result.status.value),
        _term("discrepancy_count", str(result.discrepancy_count)),
        _term("message", result.message),
        _term("duration_ms", str(result.duration_ms)),
        "</dl>",
    ]
    if details:
        rendered.extend(["<h3>details</h3>", render_value(details)])
    if sample_records:
        rendered.extend(["<h3>sample_records</h3>", _sample_records(sample_records)])
    else:
        rendered.append('<p class="empty-state">Brak próbek dla tego wyniku.</p>')
    rendered.append("</details>")
    return "\n".join(rendered)


def _sample_records(records: list[dict[str, Any]]) -> str:
    if not records:
        return '<p class="empty-state">Brak próbek.</p>'
    first_keys = sorted(records[0])
    if first_keys and all(set(record) == set(first_keys) for record in records):
        rows = [[record.get(key) for key in first_keys] for record in records]
        return _table(first_keys, rows)
    return render_value(records)


def _metadata(report: MigrationReport) -> str:
    return "\n".join(
        [
            '<section class="panel metadata">',
            "<h2>Metadane</h2>",
            '<dl class="meta-grid">',
            _term("Wersja aplikacji", __version__),
            _term("Schema version", report.schema_version),
            _term("Generator", "Data Migration Quality Gate"),
            "</dl>",
            "</section>",
        ]
    )


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return '<p class="empty-state">Brak danych do wyświetlenia.</p>'
    head = "".join(f"<th>{escape_text(header)}</th>" for header in headers)
    body_rows = []
    for row in rows:
        cells = []
        for value in row:
            rendered = value.html if isinstance(value, HtmlFragment) else render_value(value)
            cells.append(f"<td>{rendered}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return "\n".join(
        [
            '<div class="table-wrap">',
            "<table>",
            f"<thead><tr>{head}</tr></thead>",
            f"<tbody>{''.join(body_rows)}</tbody>",
            "</table>",
            "</div>",
        ]
    )


def _status_badge(status: str) -> HtmlFragment:
    status_class = escape_text(status.lower())
    label = escape_text(status)
    return HtmlFragment(f'<span class="status-badge status-{status_class}">{label}</span>')


def _term(label: str, value: Any) -> str:
    return f"<dt>{escape_text(label)}</dt><dd>{render_value(value)}</dd>"


def _normalize_json_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    return repr(value)


def _css() -> str:
    return """
:root {
  color-scheme: light dark;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #17202a;
  --muted: #5f6b7a;
  --border: #d9dee7;
  --pass: #0f766e;
  --warn: #9a6700;
  --fail: #b42318;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #111418;
    --panel: #191e24;
    --text: #eef2f7;
    --muted: #a8b3c2;
    --border: #303844;
    --pass: #5eead4;
    --warn: #facc15;
    --fail: #f97066;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.page {
  width: min(1180px, 100%);
  margin: 0 auto;
  padding: 24px;
}
.panel, .decision-panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin: 0 0 16px;
  padding: 18px;
}
.report-header p, .decision-panel p {
  color: var(--muted);
  margin: 0 0 4px;
}
h1, h2, h3 { line-height: 1.2; margin: 0 0 12px; }
h1 { font-size: 30px; }
h2 { font-size: 20px; }
h3 { font-size: 15px; margin-top: 16px; }
.decision-panel {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  border-width: 2px;
}
.decision-panel strong {
  display: block;
  font-size: clamp(28px, 5vw, 48px);
}
.status-pass, .decision-allow { border-color: var(--pass); }
.status-warn, .decision-review { border-color: var(--warn); }
.status-fail, .decision-block { border-color: var(--fail); }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}
.summary-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px;
}
.summary-card span, dt, .empty-state {
  color: var(--muted);
}
.summary-card strong {
  display: block;
  font-size: 24px;
}
.meta-grid, .detail-grid {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 8px 16px;
}
dt { font-weight: 700; }
dd { margin: 0; overflow-wrap: anywhere; }
.table-wrap { overflow-x: auto; }
table {
  width: 100%;
  border-collapse: collapse;
}
th, td {
  border-bottom: 1px solid var(--border);
  padding: 8px;
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}
th { color: var(--muted); font-weight: 700; }
.status-badge {
  border: 1px solid currentColor;
  border-radius: 999px;
  display: inline-block;
  font-weight: 700;
  padding: 2px 8px;
}
.status-badge.status-pass { color: var(--pass); }
.status-badge.status-warn { color: var(--warn); }
.status-badge.status-fail { color: var(--fail); }
details {
  border-top: 1px solid var(--border);
  padding: 12px 0;
}
summary {
  cursor: pointer;
  font-weight: 700;
  overflow-wrap: anywhere;
}
pre {
  border: 1px solid var(--border);
  border-radius: 6px;
  margin: 8px 0 0;
  overflow-x: auto;
  padding: 10px;
  white-space: pre-wrap;
}
.null-value { color: var(--muted); font-style: italic; }
@media (max-width: 640px) {
  .page { padding: 12px; }
  .decision-panel, .meta-grid, .detail-grid { grid-template-columns: 1fr; }
}
@media print {
  body { background: #fff; color: #000; }
  .panel, .decision-panel { break-inside: avoid; }
}
""".strip()
