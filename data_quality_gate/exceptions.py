"""Domain exceptions used by the CLI boundary."""


class DataQualityGateError(Exception):
    """Base class for controlled application errors."""


class ConfigurationError(DataQualityGateError):
    """Raised when YAML configuration cannot be loaded or validated."""


class DatabaseConnectionError(DataQualityGateError):
    """Raised when a source or target database connection cannot be established."""


class CheckExecutionError(DataQualityGateError):
    """Raised when a configured check cannot be executed."""


class ReportWriteError(DataQualityGateError):
    """Raised when a JSON report cannot be written."""
