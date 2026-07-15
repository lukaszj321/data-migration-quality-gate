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
    SCHEMA_MATCH = "schema_match"
    NULL_CHECK = "null_check"
    ALLOWED_VALUES = "allowed_values"
    REFERENTIAL_INTEGRITY = "referential_integrity"


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


class ReferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table: str = Field(min_length=1)
    column: str = Field(min_length=1)

    @field_validator("table", "column")
    @classmethod
    def reference_names_must_be_identifiers(cls, value: str) -> str:
        stripped = value.strip()
        if not IDENTIFIER_PATTERN.fullmatch(stripped):
            raise ValueError("must be a non-empty SQL identifier")
        return stripped


class ColumnConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    not_null: bool = False
    allowed_values: list[str] | None = None
    references: ReferenceConfig | None = None

    @field_validator("allowed_values")
    @classmethod
    def allowed_values_must_be_unique(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        if not values:
            raise ValueError("allowed_values must not be empty")
        seen: set[str] = set()
        duplicates: list[str] = []
        normalized: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value:
                raise ValueError("allowed_values entries must be non-empty strings")
            if value in seen:
                duplicates.append(value)
            seen.add(value)
            normalized.append(value)
        if duplicates:
            duplicate_list = ", ".join(sorted(set(duplicates)))
            raise ValueError(f"duplicate allowed values are not allowed: {duplicate_list}")
        return normalized


class TableConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_key: str = Field(min_length=1)
    checks: list[CheckName] = Field(min_length=1)
    columns: dict[str, ColumnConfig] = Field(default_factory=dict)

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

    @field_validator("columns")
    @classmethod
    def column_names_must_be_identifiers(
        cls, columns: dict[str, ColumnConfig]
    ) -> dict[str, ColumnConfig]:
        for column_name in columns:
            if not column_name.strip():
                raise ValueError("column names must not be blank")
            if not IDENTIFIER_PATTERN.fullmatch(column_name):
                raise ValueError(f"column name '{column_name}' must be a SQL identifier")
        return columns

    @model_validator(mode="after")
    def check_requirements_must_have_column_config(self) -> TableConfig:
        if CheckName.SCHEMA_MATCH in self.checks and not self.columns:
            raise ValueError("schema_match requires at least one configured column")
        if CheckName.NULL_CHECK in self.checks and not any(
            column.not_null for column in self.columns.values()
        ):
            raise ValueError("null_check requires at least one column with not_null: true")
        if CheckName.ALLOWED_VALUES in self.checks and not any(
            column.allowed_values for column in self.columns.values()
        ):
            raise ValueError(
                "allowed_values requires at least one column with allowed_values configured"
            )
        if CheckName.REFERENTIAL_INTEGRITY in self.checks and not any(
            column.references for column in self.columns.values()
        ):
            raise ValueError(
                "referential_integrity requires at least one column with references configured"
            )
        return self


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

    @model_validator(mode="after")
    def references_must_point_to_configured_columns(self) -> QualityGateConfig:
        for table_name, table in self.tables.items():
            for column_name, column in table.columns.items():
                if column.references is None:
                    continue
                reference = column.references
                referenced_table = self.tables.get(reference.table)
                if referenced_table is None:
                    raise ValueError(
                        f"{table_name}.{column_name} references unknown table '{reference.table}'"
                    )
                if reference.column not in referenced_table.columns:
                    raise ValueError(
                        f"{table_name}.{column_name} references unknown column "
                        f"'{reference.table}.{reference.column}'"
                    )
        return self


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
