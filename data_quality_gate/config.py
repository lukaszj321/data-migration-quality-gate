"""YAML configuration loading and validation."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from data_quality_gate.exceptions import ConfigurationError

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CheckName(StrEnum):
    ROW_COUNT = "row_count"
    MISSING_KEYS = "missing_keys"
    UNEXPECTED_KEYS = "unexpected_keys"
    DUPLICATE_KEYS = "duplicate_keys"


class MigrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    sample_limit: int = Field(default=5, ge=1)

    @field_validator("name", "source", "target")
    @classmethod
    def non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        if "://" in stripped:
            raise ValueError("must be a connection alias, not a connection string")
        return stripped

    @model_validator(mode="after")
    def source_and_target_must_differ(self) -> MigrationConfig:
        if self.source == self.target:
            raise ValueError(
                "migration.source and migration.target must refer to different aliases"
            )
        return self


class TableConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_key: str = Field(min_length=1)
    checks: list[CheckName] = Field(min_length=1)

    @field_validator("primary_key")
    @classmethod
    def primary_key_must_be_identifier(cls, value: str) -> str:
        stripped = value.strip()
        if not IDENTIFIER_PATTERN.fullmatch(stripped):
            raise ValueError("must be a non-empty SQL identifier")
        return stripped

    @field_validator("checks", mode="after")
    @classmethod
    def checks_must_be_unique(cls, checks: list[CheckName]) -> list[CheckName]:
        seen: set[CheckName] = set()
        duplicates: list[str] = []
        for check in checks:
            if check in seen:
                duplicates.append(check.value)
            seen.add(check)
        if duplicates:
            duplicate_list = ", ".join(sorted(set(duplicates)))
            raise ValueError(f"duplicate checks are not allowed: {duplicate_list}")
        return checks


class QualityGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    migration: MigrationConfig
    tables: dict[str, TableConfig] = Field(min_length=1)

    @field_validator("tables")
    @classmethod
    def table_names_must_be_identifiers(
        cls, tables: dict[str, TableConfig]
    ) -> dict[str, TableConfig]:
        for table_name in tables:
            if not table_name.strip():
                raise ValueError("table names must not be blank")
            if not IDENTIFIER_PATTERN.fullmatch(table_name):
                raise ValueError(f"table name '{table_name}' must be a SQL identifier")
        return tables


def load_config(path: str | Path) -> QualityGateConfig:
    config_path = Path(path)
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Cannot read configuration file '{config_path}'.") from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Cannot parse YAML in '{config_path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError(
            "Configuration must be a YAML mapping with migration and tables sections."
        )

    try:
        return QualityGateConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigurationError(_format_validation_error(exc)) from exc


def _format_validation_error(exc: ValidationError) -> str:
    lines = ["Invalid configuration:"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        message = str(error["msg"])
        bad_input = error.get("input")
        if isinstance(bad_input, str | int | float | bool):
            message = f"{message} (input: {bad_input})"
        lines.append(f"- {location}: {message}")
    return "\n".join(lines)


def supported_check_names() -> set[str]:
    return {check.value for check in CheckName}


def as_plain_dict(config: QualityGateConfig) -> dict[str, Any]:
    return config.model_dump(mode="json")
