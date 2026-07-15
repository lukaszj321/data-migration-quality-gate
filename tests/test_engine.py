from __future__ import annotations

from data_quality_gate.engine import aggregate_status, deployment_decision_for
from data_quality_gate.models import CheckResult, CheckStatus, DeploymentDecision


def make_result(status: CheckStatus) -> CheckResult:
    return CheckResult(
        check_name="row_count",
        table="customers",
        status=status,
        discrepancy_count=0,
        message="ok",
        sample_records=[],
        duration_ms=0,
    )


def test_aggregate_pass() -> None:
    assert aggregate_status([make_result(CheckStatus.PASS)]) == CheckStatus.PASS


def test_aggregate_warn() -> None:
    assert (
        aggregate_status([make_result(CheckStatus.PASS), make_result(CheckStatus.WARN)])
        == CheckStatus.WARN
    )


def test_aggregate_fail() -> None:
    assert (
        aggregate_status([make_result(CheckStatus.WARN), make_result(CheckStatus.FAIL)])
        == CheckStatus.FAIL
    )


def test_deployment_decisions() -> None:
    assert deployment_decision_for(CheckStatus.PASS) == DeploymentDecision.ALLOW
    assert deployment_decision_for(CheckStatus.WARN) == DeploymentDecision.REVIEW
    assert deployment_decision_for(CheckStatus.FAIL) == DeploymentDecision.BLOCK
