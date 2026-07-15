from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, text

from data_quality_gate.config import load_config
from data_quality_gate.engine import run_checks, run_quality_gate
from data_quality_gate.models import CheckStatus, DeploymentDecision


def test_run_checks_builds_report(sqlite_pair: tuple[Engine, Engine], tmp_path: Path) -> None:
    source, target = sqlite_pair
    _insert(source, ["A", "B"])
    _insert(target, ["A", "C"])
    config_path = tmp_path / "migration.yaml"
    config_path.write_text(
        """
migration:
  name: sqlite-migration
  source: source_db
  target: target_db
  sample_limit: 5
tables:
  items:
    primary_key: item_id
    checks: [row_count, missing_keys, unexpected_keys, duplicate_keys]
""".strip(),
        encoding="utf-8",
    )

    report = run_checks(load_config(config_path), source, target)

    assert report.summary.status == CheckStatus.FAIL
    assert report.summary.deployment_decision == DeploymentDecision.BLOCK
    assert report.summary.checks_total == 4
    assert [result.check_name for result in report.results] == [
        "row_count",
        "missing_keys",
        "unexpected_keys",
        "duplicate_keys",
    ]


def test_run_quality_gate_uses_database_aliases(
    sqlite_pair: tuple[Engine, Engine], tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    source, target = sqlite_pair
    source.dispose()
    target.dispose()
    source_path = tmp_path / "source.sqlite"
    target_path = tmp_path / "target.sqlite"
    for db_path in (source_path, target_path):
        engine = _file_engine(db_path)
        try:
            _create_items(engine)
            _insert(engine, ["A"])
        finally:
            engine.dispose()
    monkeypatch.setenv("DQG_SOURCE_DB_URL", f"sqlite+pysqlite:///{source_path.as_posix()}")
    monkeypatch.setenv("DQG_TARGET_DB_URL", f"sqlite+pysqlite:///{target_path.as_posix()}")
    config_path = tmp_path / "migration.yaml"
    config_path.write_text(
        """
migration:
  name: sqlite-migration
  source: source_db
  target: target_db
tables:
  items:
    primary_key: item_id
    checks: [row_count]
""".strip(),
        encoding="utf-8",
    )

    report = run_quality_gate(load_config(config_path))

    assert report.summary.status == CheckStatus.PASS


def _file_engine(path: Path) -> Engine:
    return create_engine(f"sqlite+pysqlite:///{path.as_posix()}", future=True)


def _create_items(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE items (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id VARCHAR(32),
                    payload VARCHAR(120)
                )
                """
            )
        )


def _insert(engine: Engine, keys: list[str]) -> None:
    with engine.begin() as connection:
        for key in keys:
            connection.execute(
                text("INSERT INTO items (item_id, payload) VALUES (:key, :payload)"),
                {"key": key, "payload": f"payload-{key}"},
            )
