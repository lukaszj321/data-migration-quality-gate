from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from data_quality_gate.html_reporting import render_html_report, render_value
from data_quality_gate.models import (
    CheckResult,
    CheckStatus,
    DeploymentDecision,
    MigrationReport,
    MigrationSummary,
)


def test_render_html_report_contains_document_summary_and_results() -> None:
    report = _report()

    html = render_html_report(report)

    assert html.startswith("<!DOCTYPE html>")
    assert '<meta charset="utf-8">' in html
    assert "Migracja płatności" in html
    assert "FAIL" in html
    assert "BLOCK" in html
    assert "Kontrole razem" in html
    assert "PASS" in html
    assert "WARN" in html
    assert "Nieudane kontrole" in html
    assert "Wszystkie wyniki" in html
    assert "Szczegóły wyników" in html
    assert "row_count" in html
    assert "numeric_tolerance" in html
    assert "schema_match" in html


def test_render_html_report_handles_empty_failed_checks_and_empty_samples() -> None:
    report = _report(status=CheckStatus.PASS, decision=DeploymentDecision.ALLOW)

    html = render_html_report(report)

    assert "Brak kontroli ze statusem FAIL." in html
    assert "Brak próbek dla tego wyniku." in html
    assert "ALLOW" in html


def test_render_html_report_escapes_html_and_has_no_active_script() -> None:
    report = _report(
        message='<script>alert("x")</script> & payload',
        sample_value='<script>alert("x")</script>',
    )

    html = render_html_report(report)

    assert "<script" not in html.lower()
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert "&amp; payload" in html


def test_render_html_report_uses_no_external_resources_or_javascript() -> None:
    html = render_html_report(_report())
    lowered = html.lower()

    assert "http://" not in lowered
    assert "https://" not in lowered
    assert "javascript:" not in lowered
    assert "<script" not in lowered
    assert " src=" not in lowered
    assert " href=" not in lowered


def test_render_value_formats_scalars_and_nested_structures() -> None:
    timestamp = datetime(2024, 1, 1, 12, 30, tzinfo=UTC)

    assert render_value(None) == '<span class="null-value">NULL</span>'
    assert render_value(True) == "true"
    assert render_value(Decimal("10.0100")) == "10.0100"
    assert "2024-01-01T12:30:00+00:00" in render_value(timestamp)
    nested = render_value({"amount": Decimal("1.20"), "when": timestamp, "items": [None]})
    assert "<pre>" in nested
    assert "&quot;amount&quot;: &quot;1.20&quot;" in nested
    assert "&quot;items&quot;: [" in nested
    assert "NULL" not in nested


def test_render_html_report_is_deterministic_for_same_model() -> None:
    report = _report()

    assert render_html_report(report) == render_html_report(report)


def _report(
    *,
    status: CheckStatus = CheckStatus.FAIL,
    decision: DeploymentDecision = DeploymentDecision.BLOCK,
    message: str = "Kwota poza tolerancją",
    sample_value: str = "Zażółć gęślą jaźń",
) -> MigrationReport:
    started = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    finished = datetime(2024, 1, 1, 12, 0, 1, tzinfo=UTC)
    pass_result = CheckResult(
        check_name="row_count",
        table="accounts",
        status=CheckStatus.PASS,
        discrepancy_count=0,
        message="Row counts match.",
        sample_records=[],
        duration_ms=1,
    )
    warn_result = CheckResult(
        check_name="unexpected_keys",
        table="transactions",
        status=CheckStatus.WARN,
        discrepancy_count=1,
        message="Found unexpected key.",
        sample_records=[{"transaction_id": "T999"}],
        duration_ms=2,
    )
    fail_result = CheckResult(
        check_name="numeric_tolerance",
        table="transactions",
        status=status,
        discrepancy_count=1 if status == CheckStatus.FAIL else 0,
        message=message,
        sample_records=[
            {
                "transaction_id": "T004",
                "amount": Decimal("-25.00"),
                "occurred_at": started,
                "note": sample_value,
                "empty": None,
            }
        ],
        duration_ms=3,
    )
    schema_result = CheckResult(
        check_name="schema_match",
        table="transactions",
        status=CheckStatus.PASS,
        discrepancy_count=0,
        message="Schema matches.",
        sample_records=[{"column": "description"}, {"issue": "heterogeneous"}],
        duration_ms=4,
    )
    results = [pass_result, warn_result, fail_result, schema_result]
    failed = [result for result in results if result.status == CheckStatus.FAIL]
    summary = MigrationSummary(
        migration_name="Migracja płatności",
        status=status,
        deployment_decision=decision,
        checks_total=len(results),
        checks_passed=sum(result.status == CheckStatus.PASS for result in results),
        checks_warned=sum(result.status == CheckStatus.WARN for result in results),
        checks_failed=sum(result.status == CheckStatus.FAIL for result in results),
        started_at=started,
        finished_at=finished,
        duration_ms=1000,
    )
    return MigrationReport(summary=summary, failed_checks=failed, results=results)
