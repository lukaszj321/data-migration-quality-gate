from __future__ import annotations

from data_quality_gate.safety import redact_secrets, safe_error_message


def test_redact_secrets_masks_database_url_password() -> None:
    message = (
        "failed for postgresql+psycopg://demo_user:super-secret-password@localhost:5433/source_db"
    )

    redacted = redact_secrets(message)

    assert "super-secret-password" not in redacted
    assert "demo_user:[REDACTED]@localhost:5433/source_db" in redacted


def test_redact_secrets_masks_secret_query_parameters() -> None:
    message = "postgresql://demo@localhost/db?sslmode=require&token=secret-token&password=pw"

    redacted = redact_secrets(message)

    assert "secret-token" not in redacted
    assert "password=pw" not in redacted
    assert "token=[REDACTED]" in redacted
    assert "password=[REDACTED]" in redacted


def test_redact_secrets_masks_environment_secret_values(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DQG_TEST_PASSWORD", "env-secret")

    assert redact_secrets("value env-secret leaked") == "value [REDACTED] leaked"


def test_safe_error_message_redacts_exception_text() -> None:
    error = RuntimeError("password=super-secret-password")

    assert "super-secret-password" not in safe_error_message(error)
