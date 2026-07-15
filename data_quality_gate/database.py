"""Database connection helpers."""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from data_quality_gate.exceptions import DatabaseConnectionError

ALIAS_TO_ENV = {
    "source_db": "DQG_SOURCE_DB_URL",
    "target_db": "DQG_TARGET_DB_URL",
}


def connection_url_for_alias(alias: str) -> str:
    env_name = ALIAS_TO_ENV.get(alias)
    if env_name is None:
        expected = ", ".join(sorted(ALIAS_TO_ENV))
        raise DatabaseConnectionError(
            f"Unknown database alias '{alias}'. Expected one of: {expected}."
        )

    value = os.getenv(env_name)
    if not value:
        raise DatabaseConnectionError(f"Environment variable {env_name} is not set.")
    return value


def build_engine(alias: str) -> Engine:
    url = connection_url_for_alias(alias)
    try:
        return create_engine(url, future=True, pool_pre_ping=True)
    except SQLAlchemyError as exc:
        raise DatabaseConnectionError(
            f"Cannot create database engine for alias '{alias}'."
        ) from exc


def verify_connection(engine: Engine, alias: str) -> None:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise DatabaseConnectionError(f"Cannot connect to database alias '{alias}'.") from exc
