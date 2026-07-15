from __future__ import annotations

from sqlalchemy import Engine, text

from data_quality_gate.checks import (
    allowed_values,
    duplicate_keys,
    missing_keys,
    null_check,
    referential_integrity,
    row_count,
    schema_match,
    unexpected_keys,
)
from data_quality_gate.checks.base import CheckContext
from data_quality_gate.checks.schema_match import ColumnSchema
from data_quality_gate.config import CheckName, ColumnConfig, ReferenceConfig, TableConfig
from data_quality_gate.models import CheckStatus


def test_row_count_detects_mismatch(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _insert(source, ["B", "A"])
    _insert(target, ["A"])

    result = row_count.run(_context(source, target, sample_limit=5))

    assert result.status == CheckStatus.FAIL
    assert result.sample_records == [{"source_count": 2, "target_count": 1, "difference": -1}]


def test_missing_keys_limits_and_sorts_samples(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _insert(source, ["C", "A", "B", "D"])
    _insert(target, ["D"])

    result = missing_keys.run(_context(source, target, sample_limit=2))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 3
    assert result.sample_records == [{"item_id": "A"}, {"item_id": "B"}]


def test_unexpected_keys_warns_and_sorts_samples(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _insert(source, ["B"])
    _insert(target, ["C", "A", "B"])

    result = unexpected_keys.run(_context(source, target, sample_limit=5))

    assert result.status == CheckStatus.WARN
    assert result.discrepancy_count == 2
    assert result.sample_records == [{"item_id": "A"}, {"item_id": "C"}]


def test_duplicate_keys_distinguishes_source_and_target(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _insert(source, ["A", "A", "B"])
    _insert(target, ["C", "C", "C"])

    result = duplicate_keys.run(_context(source, target, sample_limit=5))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 2
    assert result.sample_records == [
        {"database": "source", "item_id": "A", "duplicate_count": 2},
        {"database": "target", "item_id": "C", "duplicate_count": 3},
    ]


def test_empty_tables_pass(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    context = _context(source, target, sample_limit=5)

    assert row_count.run(context).status == CheckStatus.PASS
    assert missing_keys.run(context).status == CheckStatus.PASS
    assert unexpected_keys.run(context).status == CheckStatus.PASS
    assert duplicate_keys.run(context).status == CheckStatus.PASS


def test_null_check_detects_nulls_with_limit(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _insert(source, ["A", "B"])
    _insert(target, ["C"])
    with source.begin() as connection:
        connection.execute(text("UPDATE items SET payload = NULL WHERE item_id IN ('A', 'B')"))
    with target.begin() as connection:
        connection.execute(text("UPDATE items SET payload = NULL WHERE item_id = 'C'"))

    result = null_check.run(_configured_context(source, target, sample_limit=2))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 3
    assert len(result.sample_records) == 2
    assert result.sample_records[0]["database"] == "source"


def test_allowed_values_detects_bad_values_and_ignores_null(
    sqlite_pair: tuple[Engine, Engine],
) -> None:
    source, target = sqlite_pair
    _insert(source, ["A", "B"])
    _insert(target, ["C", "D"])
    with source.begin() as connection:
        connection.execute(text("UPDATE items SET payload = 'BAD' WHERE item_id = 'A'"))
        connection.execute(text("UPDATE items SET payload = NULL WHERE item_id = 'B'"))
    with target.begin() as connection:
        connection.execute(text("UPDATE items SET payload = 'ZZZ' WHERE item_id = 'C'"))
        connection.execute(text("UPDATE items SET payload = 'OK' WHERE item_id = 'D'"))

    result = allowed_values.run(_configured_context(source, target, sample_limit=5))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 2
    assert [sample["value"] for sample in result.sample_records] == ["BAD", "ZZZ"]


def test_referential_integrity_detects_orphans(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    for engine in (source, target):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE parents (
                        row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        parent_id VARCHAR(32)
                    )
                    """
                )
            )
    with source.begin() as connection:
        connection.execute(text("INSERT INTO parents (parent_id) VALUES ('P1')"))
        connection.execute(text("INSERT INTO items (item_id, payload) VALUES ('A', 'NOPE')"))
    with target.begin() as connection:
        connection.execute(text("INSERT INTO parents (parent_id) VALUES ('P1'), ('P1')"))
        connection.execute(text("INSERT INTO items (item_id, payload) VALUES ('B', 'P1')"))

    result = referential_integrity.run(_reference_context(source, target))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 1
    assert result.sample_records[0]["database"] == "source"


def test_schema_match_compares_loaded_schemas(
    monkeypatch, sqlite_pair: tuple[Engine, Engine]
) -> None:  # type: ignore[no-untyped-def]
    source, target = sqlite_pair
    source_schema = {
        "id": ColumnSchema("id", "character varying", 20, None, None, False),
        "amount": ColumnSchema("amount", "numeric", None, 10, 2, True),
        "payload": ColumnSchema("payload", "character varying", 255, None, None, True),
    }
    target_schema = {
        "id": ColumnSchema("id", "character varying", 20, None, None, True),
        "payload": ColumnSchema("payload", "character varying", 80, None, None, True),
        "extra": ColumnSchema("extra", "text", None, None, None, True),
    }
    monkeypatch.setattr(
        schema_match,
        "_load_schema",
        lambda engine, table: source_schema if engine is source else target_schema,
    )

    result = schema_match.run(_schema_configured_context(source, target))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 4
    assert [sample["issue"] for sample in result.sample_records] == [
        "missing_column_in_target",
        "nullability_mismatch",
        "length_mismatch",
        "unexpected_column_in_target",
    ]


def _context(source: Engine, target: Engine, sample_limit: int) -> CheckContext:
    return CheckContext(
        source_engine=source,
        target_engine=target,
        table="items",
        primary_key="item_id",
        sample_limit=sample_limit,
    )


def _configured_context(source: Engine, target: Engine, sample_limit: int) -> CheckContext:
    table_config = TableConfig(
        primary_key="item_id",
        checks=[CheckName.NULL_CHECK, CheckName.ALLOWED_VALUES],
        columns={
            "item_id": ColumnConfig(not_null=True),
            "payload": ColumnConfig(not_null=True, allowed_values=["OK"]),
        },
    )
    return CheckContext(
        source_engine=source,
        target_engine=target,
        table="items",
        primary_key="item_id",
        sample_limit=sample_limit,
        table_config=table_config,
        all_tables={"items": table_config},
    )


def _reference_context(source: Engine, target: Engine) -> CheckContext:
    parent_config = TableConfig(
        primary_key="parent_id",
        checks=[CheckName.SCHEMA_MATCH],
        columns={"parent_id": ColumnConfig(not_null=True)},
    )
    child_config = TableConfig(
        primary_key="item_id",
        checks=[CheckName.REFERENTIAL_INTEGRITY],
        columns={
            "item_id": ColumnConfig(not_null=True),
            "payload": ColumnConfig(
                references=ReferenceConfig(table="parents", column="parent_id")
            ),
        },
    )
    return CheckContext(
        source_engine=source,
        target_engine=target,
        table="items",
        primary_key="item_id",
        sample_limit=5,
        table_config=child_config,
        all_tables={"parents": parent_config, "items": child_config},
    )


def _schema_configured_context(source: Engine, target: Engine) -> CheckContext:
    table_config = TableConfig(
        primary_key="id",
        checks=[CheckName.SCHEMA_MATCH],
        columns={
            "id": ColumnConfig(not_null=True),
            "amount": ColumnConfig(),
            "payload": ColumnConfig(),
        },
    )
    return CheckContext(
        source_engine=source,
        target_engine=target,
        table="items",
        primary_key="id",
        sample_limit=10,
        table_config=table_config,
        all_tables={"items": table_config},
    )


def _insert(engine: Engine, keys: list[str]) -> None:
    with engine.begin() as connection:
        for key in keys:
            connection.execute(
                text("INSERT INTO items (item_id, payload) VALUES (:key, :payload)"),
                {"key": key, "payload": f"payload-{key}"},
            )
