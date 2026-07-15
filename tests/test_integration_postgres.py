from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine

from data_quality_gate.checks import duplicate_keys, missing_keys, row_count, unexpected_keys
from data_quality_gate.checks.base import CheckContext
from data_quality_gate.config import load_config
from data_quality_gate.engine import run_checks
from data_quality_gate.models import CheckStatus

pytestmark = pytest.mark.integration


@pytest.fixture()
def postgres_context() -> CheckContext:  # type: ignore[misc]
    source_url = os.getenv("DQG_SOURCE_DB_URL")
    target_url = os.getenv("DQG_TARGET_DB_URL")
    if not source_url or not target_url:
        pytest.skip("DQG_SOURCE_DB_URL and DQG_TARGET_DB_URL are required for integration tests.")

    source = create_engine(source_url, future=True)
    target = create_engine(target_url, future=True)
    try:
        yield CheckContext(source, target, "transactions", "transaction_id", 5)
    finally:
        source.dispose()
        target.dispose()


def test_demo_row_count_passes_despite_other_errors(postgres_context: CheckContext) -> None:
    result = row_count.run(postgres_context)
    assert result.status == CheckStatus.PASS


def test_demo_missing_keys(postgres_context: CheckContext) -> None:
    result = missing_keys.run(postgres_context)
    assert result.status == CheckStatus.FAIL
    assert result.sample_records == [{"transaction_id": "T006"}, {"transaction_id": "T014"}]


def test_demo_unexpected_keys(postgres_context: CheckContext) -> None:
    result = unexpected_keys.run(postgres_context)
    assert result.status == CheckStatus.WARN
    assert result.sample_records == [{"transaction_id": "T999"}]


def test_demo_duplicate_keys(postgres_context: CheckContext) -> None:
    result = duplicate_keys.run(postgres_context)
    assert result.status == CheckStatus.FAIL
    assert result.sample_records == [
        {"database": "target", "transaction_id": "T003", "duplicate_count": 2}
    ]


def test_demo_full_gate_has_pass_warn_and_fail() -> None:
    source_url = os.getenv("DQG_SOURCE_DB_URL")
    target_url = os.getenv("DQG_TARGET_DB_URL")
    if not source_url or not target_url:
        pytest.skip("DQG_SOURCE_DB_URL and DQG_TARGET_DB_URL are required for integration tests.")

    config = load_config("migration.yaml")
    source = create_engine(source_url, future=True)
    target = create_engine(target_url, future=True)
    try:
        report = run_checks(config, source, target)
    finally:
        source.dispose()
        target.dispose()

    statuses = {result.status for result in report.results}
    assert report.summary.status == CheckStatus.FAIL
    assert CheckStatus.PASS in statuses
    assert CheckStatus.WARN in statuses
    assert CheckStatus.FAIL in statuses
