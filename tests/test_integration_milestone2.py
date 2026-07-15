from __future__ import annotations

from sqlalchemy import Engine, text

from data_quality_gate.checks import (
    allowed_values,
    null_check,
    referential_integrity,
    schema_match,
)
from data_quality_gate.checks.base import CheckContext
from data_quality_gate.config import CheckName, ColumnConfig, ReferenceConfig, TableConfig
from data_quality_gate.models import CheckStatus

pytestmark = __import__("pytest").mark.integration


def test_schema_match_passes_for_matching_schema(postgres_pair: tuple[Engine, Engine]) -> None:
    source, target = postgres_pair
    _create_schema_table(
        source,
        target,
        "m2_schema_ok",
        _schema_sql("m2_schema_ok"),
        _schema_sql("m2_schema_ok"),
    )

    result = schema_match.run(_schema_context(source, target, "m2_schema_ok"))

    assert result.status == CheckStatus.PASS


def test_schema_match_detects_missing_column(postgres_pair: tuple[Engine, Engine]) -> None:
    source, target = postgres_pair
    _create_schema_table(
        source,
        target,
        "m2_schema_missing",
        _schema_sql("m2_schema_missing"),
        """
        CREATE TABLE m2_schema_missing (
            row_id BIGSERIAL PRIMARY KEY,
            id VARCHAR(10) NOT NULL
        )
        """,
    )

    result = schema_match.run(_schema_context(source, target, "m2_schema_missing"))

    assert result.status == CheckStatus.FAIL
    assert any(sample["issue"] == "missing_column_in_target" for sample in result.sample_records)


def test_schema_match_detects_type_length_and_nullability(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_schema_table(
        source,
        target,
        "m2_schema_diff",
        _schema_sql("m2_schema_diff"),
        """
        CREATE TABLE m2_schema_diff (
            row_id BIGSERIAL PRIMARY KEY,
            id VARCHAR(20),
            payload TEXT,
            amount NUMERIC(12,2),
            required_value VARCHAR(20)
        )
        """,
    )

    result = schema_match.run(_schema_context(source, target, "m2_schema_diff"))
    issues = {sample["issue"] for sample in result.sample_records}

    assert result.status == CheckStatus.FAIL
    assert {"type_mismatch", "length_mismatch", "nullability_mismatch"} <= issues


def test_schema_match_handles_empty_tables(postgres_pair: tuple[Engine, Engine]) -> None:
    source, target = postgres_pair
    _create_schema_table(
        source,
        target,
        "m2_schema_empty",
        _schema_sql("m2_schema_empty"),
        _schema_sql("m2_schema_empty"),
    )

    result = schema_match.run(_schema_context(source, target, "m2_schema_empty"))

    assert result.status == CheckStatus.PASS


def test_null_check_passes_without_nulls(postgres_pair: tuple[Engine, Engine]) -> None:
    source, target = postgres_pair
    _create_value_table(source, target, "m2_null_ok")
    _insert_values(source, "m2_null_ok", [("A", "PLN"), ("B", "EUR")])
    _insert_values(target, "m2_null_ok", [("A", "PLN")])

    result = null_check.run(_value_context(source, target, "m2_null_ok"))

    assert result.status == CheckStatus.PASS


def test_null_check_detects_source_and_target_and_limits_samples(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_value_table(source, target, "m2_null_bad")
    _insert_values(source, "m2_null_bad", [("A", None), ("B", None)])
    _insert_values(target, "m2_null_bad", [("C", None), ("D", None)])

    result = null_check.run(_value_context(source, target, "m2_null_bad", sample_limit=2))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 4
    assert len(result.sample_records) == 2
    assert result.sample_records[0]["database"] == "source"


def test_null_check_handles_empty_tables(postgres_pair: tuple[Engine, Engine]) -> None:
    source, target = postgres_pair
    _create_value_table(source, target, "m2_null_empty")

    result = null_check.run(_value_context(source, target, "m2_null_empty"))

    assert result.status == CheckStatus.PASS


def test_allowed_values_passes_and_ignores_null(postgres_pair: tuple[Engine, Engine]) -> None:
    source, target = postgres_pair
    _create_value_table(source, target, "m2_allowed_ok")
    _insert_values(source, "m2_allowed_ok", [("A", "PLN"), ("B", None)])
    _insert_values(target, "m2_allowed_ok", [("C", "EUR")])

    result = allowed_values.run(_value_context(source, target, "m2_allowed_ok"))

    assert result.status == CheckStatus.PASS


def test_allowed_values_detects_source_and_target_values(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_value_table(source, target, "m2_allowed_bad")
    _insert_values(source, "m2_allowed_bad", [("A", "GBP")])
    _insert_values(target, "m2_allowed_bad", [("B", "XYZ"), ("C", "CHF")])

    result = allowed_values.run(_value_context(source, target, "m2_allowed_bad", sample_limit=5))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 3
    assert [sample["value"] for sample in result.sample_records] == ["GBP", "CHF", "XYZ"]


def test_referential_integrity_passes_for_valid_relation(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_parent_child(source, target, "m2_ref_ok_parent", "m2_ref_ok_child")
    _insert_parent_child(source, "m2_ref_ok_parent", "m2_ref_ok_child", [("P1",)], [("C1", "P1")])
    _insert_parent_child(target, "m2_ref_ok_parent", "m2_ref_ok_child", [("P1",)], [("C1", "P1")])

    result = referential_integrity.run(
        _reference_context(source, target, "m2_ref_ok_parent", "m2_ref_ok_child")
    )

    assert result.status == CheckStatus.PASS


def test_referential_integrity_detects_orphans_and_ignores_nulls(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_parent_child(source, target, "m2_ref_bad_parent", "m2_ref_bad_child")
    _insert_parent_child(
        source,
        "m2_ref_bad_parent",
        "m2_ref_bad_child",
        [("P1",)],
        [("C1", "NOPE"), ("C2", None)],
    )
    _insert_parent_child(
        target,
        "m2_ref_bad_parent",
        "m2_ref_bad_child",
        [("P1",), ("P1",)],
        [("C3", "MISSING")],
    )

    result = referential_integrity.run(
        _reference_context(source, target, "m2_ref_bad_parent", "m2_ref_bad_child")
    )

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 2
    assert [sample["database"] for sample in result.sample_records] == ["source", "target"]


def test_referential_integrity_handles_empty_child_and_parent(
    postgres_pair: tuple[Engine, Engine],
) -> None:
    source, target = postgres_pair
    _create_parent_child(source, target, "m2_ref_empty_parent", "m2_ref_empty_child")
    _insert_parent_child(source, "m2_ref_empty_parent", "m2_ref_empty_child", [], [])
    _insert_parent_child(target, "m2_ref_empty_parent", "m2_ref_empty_child", [], [("C1", "P1")])

    empty_child = referential_integrity.run(
        _reference_context(source, source, "m2_ref_empty_parent", "m2_ref_empty_child")
    )
    empty_parent = referential_integrity.run(
        _reference_context(source, target, "m2_ref_empty_parent", "m2_ref_empty_child")
    )

    assert empty_child.status == CheckStatus.PASS
    assert empty_parent.status == CheckStatus.FAIL


def _create_schema_table(
    source: Engine, target: Engine, table: str, source_sql: str, target_sql: str
) -> None:
    for engine, sql in ((source, source_sql), (target, target_sql)):
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
            connection.execute(text(sql))


def _schema_sql(table: str) -> str:
    return f"""
    CREATE TABLE {table} (
        row_id BIGSERIAL PRIMARY KEY,
        id VARCHAR(20) NOT NULL,
        payload VARCHAR(20),
        amount NUMERIC(10,2),
        required_value VARCHAR(20) NOT NULL
    )
    """


def _schema_context(source: Engine, target: Engine, table: str) -> CheckContext:
    table_config = TableConfig(
        primary_key="id",
        checks=[CheckName.SCHEMA_MATCH],
        columns={
            "id": ColumnConfig(not_null=True),
            "payload": ColumnConfig(),
            "amount": ColumnConfig(),
            "required_value": ColumnConfig(not_null=True),
        },
    )
    return CheckContext(source, target, table, "id", 10, table_config, {table: table_config})


def _create_value_table(source: Engine, target: Engine, table: str) -> None:
    sql = f"""
    CREATE TABLE {table} (
        row_id BIGSERIAL PRIMARY KEY,
        id VARCHAR(20),
        currency VARCHAR(3)
    )
    """
    for engine in (source, target):
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {table}"))
            connection.execute(text(sql))


def _insert_values(engine: Engine, table: str, rows: list[tuple[str, str | None]]) -> None:
    with engine.begin() as connection:
        for row_id, currency in rows:
            connection.execute(
                text(f"INSERT INTO {table} (id, currency) VALUES (:id, :currency)"),
                {"id": row_id, "currency": currency},
            )


def _value_context(
    source: Engine, target: Engine, table: str, sample_limit: int = 5
) -> CheckContext:
    table_config = TableConfig(
        primary_key="id",
        checks=[CheckName.NULL_CHECK, CheckName.ALLOWED_VALUES],
        columns={
            "id": ColumnConfig(not_null=True),
            "currency": ColumnConfig(not_null=True, allowed_values=["PLN", "EUR"]),
        },
    )
    return CheckContext(
        source, target, table, "id", sample_limit, table_config, {table: table_config}
    )


def _create_parent_child(
    source: Engine, target: Engine, parent_table: str, child_table: str
) -> None:
    for engine in (source, target):
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS {child_table}"))
            connection.execute(text(f"DROP TABLE IF EXISTS {parent_table}"))
            connection.execute(
                text(
                    f"""
                    CREATE TABLE {parent_table} (
                        row_id BIGSERIAL PRIMARY KEY,
                        parent_id VARCHAR(20)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    f"""
                    CREATE TABLE {child_table} (
                        row_id BIGSERIAL PRIMARY KEY,
                        child_id VARCHAR(20),
                        parent_id VARCHAR(20)
                    )
                    """
                )
            )


def _insert_parent_child(
    engine: Engine,
    parent_table: str,
    child_table: str,
    parents: list[tuple[str]],
    children: list[tuple[str, str | None]],
) -> None:
    with engine.begin() as connection:
        for (parent_id,) in parents:
            connection.execute(
                text(f"INSERT INTO {parent_table} (parent_id) VALUES (:parent_id)"),
                {"parent_id": parent_id},
            )
        for child_id, parent_id in children:
            connection.execute(
                text(
                    f"INSERT INTO {child_table} (child_id, parent_id) "
                    "VALUES (:child_id, :parent_id)"
                ),
                {"child_id": child_id, "parent_id": parent_id},
            )


def _reference_context(
    source: Engine, target: Engine, parent_table: str, child_table: str
) -> CheckContext:
    parent_config = TableConfig(
        primary_key="parent_id",
        checks=[CheckName.SCHEMA_MATCH],
        columns={"parent_id": ColumnConfig(not_null=True)},
    )
    child_config = TableConfig(
        primary_key="child_id",
        checks=[CheckName.REFERENTIAL_INTEGRITY],
        columns={
            "child_id": ColumnConfig(not_null=True),
            "parent_id": ColumnConfig(
                references=ReferenceConfig(table=parent_table, column="parent_id")
            ),
        },
    )
    return CheckContext(
        source,
        target,
        child_table,
        "child_id",
        5,
        child_config,
        {parent_table: parent_config, child_table: child_config},
    )
