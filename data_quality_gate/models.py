"""Public result models for quality gate reports."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CheckStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class DeploymentDecision(StrEnum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_name: str
    table: str
    status: CheckStatus
    discrepancy_count: int = Field(ge=0)
    message: str
    sample_records: list[dict[str, Any]]
    duration_ms: int = Field(ge=0)


class MigrationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    migration_name: str
    status: CheckStatus
    deployment_decision: DeploymentDecision
    checks_total: int = Field(ge=0)
    checks_passed: int = Field(ge=0)
    checks_warned: int = Field(ge=0)
    checks_failed: int = Field(ge=0)
    started_at: datetime
    finished_at: datetime
    duration_ms: int = Field(ge=0)


class MigrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    summary: MigrationSummary
    failed_checks: list[CheckResult]
    results: list[CheckResult]
