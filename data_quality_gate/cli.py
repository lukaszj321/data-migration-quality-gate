"""Command line interface for Data Migration Quality Gate."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from data_quality_gate import __version__
from data_quality_gate.config import load_config
from data_quality_gate.engine import run_quality_gate
from data_quality_gate.exceptions import (
    CheckExecutionError,
    ConfigurationError,
    DatabaseConnectionError,
    ReportWriteError,
)
from data_quality_gate.models import CheckStatus
from data_quality_gate.reporting import format_summary, write_json_report

EXIT_PASS = 0
EXIT_WARN = 1
EXIT_FAIL = 2
EXIT_INVALID_CONFIG = 3
EXIT_TECHNICAL_FAILURE = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="data-quality-gate")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a migration YAML file.")
    validate_parser.add_argument("config_path")

    run_parser = subparsers.add_parser("run", help="Run configured data quality checks.")
    run_parser.add_argument("config_path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            load_config(args.config_path)
            print(f"Configuration is valid: {args.config_path}")
            return EXIT_PASS

        if args.command == "run":
            config = load_config(args.config_path)
            report = run_quality_gate(config)
            report_path = write_json_report(report)
            print(format_summary(report, report_path))
            return exit_code_for_status(report.summary.status)

    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    except (DatabaseConnectionError, CheckExecutionError, ReportWriteError) as exc:
        print(f"Technical failure: {exc}", file=sys.stderr)
        return EXIT_TECHNICAL_FAILURE
    except Exception as exc:
        if os.getenv("DQG_DEBUG"):
            raise
        print(f"Technical failure: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return EXIT_TECHNICAL_FAILURE

    parser.error("Unsupported command.")
    return EXIT_TECHNICAL_FAILURE


def exit_code_for_status(status: CheckStatus) -> int:
    if status == CheckStatus.PASS:
        return EXIT_PASS
    if status == CheckStatus.WARN:
        return EXIT_WARN
    return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
