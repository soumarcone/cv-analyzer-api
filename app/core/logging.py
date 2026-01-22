"""Logging utilities with JSON formatting, redaction, and request correlation.

This module centralizes logging configuration, including:
- Context-aware request_id propagation via contextvars
- Sensitive data redaction on log records
- JSON formatter for machine-friendly logs
- Configurable stdout/file handlers with rotation support
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from logging import LogRecord
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.core.config import LogSettings, settings

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Default sensitive keys to redact from structured fields
SENSITIVE_KEYS_DEFAULT: set[str] = {
    "api_key",
    "x-api-key",
    "authorization",
    "token",
    "secret",
    "password",
    "llm_api_key",
    "app_api_keys",
    "cookie",
    "set-cookie",
    "cv_text",
    "job_text",
    "prompt",
    "completion",
    "base_url",
}

# Logging fields we intentionally exclude from extra payload capture
_EXCLUDED_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "stack",
}


def set_request_id(request_id: str | None) -> None:
    """Store the current request id in a context variable.

    Args:
        request_id: Correlation identifier to associate with subsequent logs.
    """

    _request_id_var.set(request_id)


def get_request_id() -> str | None:
    """Fetch the current request id from context.

    Returns:
        Optional request id string if previously set.
    """

    return _request_id_var.get()


def clear_request_id() -> None:
    """Clear any stored request id from context."""

    _request_id_var.set(None)


def _is_sensitive_key(key: str, sensitive_keys: set[str]) -> bool:
    """Check if a key is considered sensitive.

    Args:
        key: Field name on the log record.
        sensitive_keys: Set of keys that must be redacted.

    Returns:
        True if the key must be redacted.
    """

    return key.lower() in sensitive_keys


def _redact_value(value: Any, sensitive_keys: set[str]) -> Any:
    """Recursively redact sensitive values within mappings and sequences.

    Args:
        value: Arbitrary value from log record extras.
        sensitive_keys: Set of keys that must be redacted.

    Returns:
        The value with sensitive fields replaced by "[REDACTED]".
    """

    if isinstance(value, Mapping):
        return {
            k: "[REDACTED]"
            if _is_sensitive_key(k, sensitive_keys)
            else _redact_value(v, sensitive_keys)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(_redact_value(v, sensitive_keys) for v in value)
    return value


def _sanitize_record(record: LogRecord, sensitive_keys: set[str]) -> dict[str, Any]:
    """Convert a LogRecord to a dict while redacting sensitive fields.

    Args:
        record: LogRecord instance to sanitize.
        sensitive_keys: Set of keys that must be redacted.

    Returns:
        Dict with safe, redacted fields ready for formatting.
    """

    data: dict[str, Any] = {}

    for key, value in record.__dict__.items():
        if key in _EXCLUDED_ATTRS or key.startswith("_"):
            continue
        if _is_sensitive_key(key, sensitive_keys):
            data[key] = "[REDACTED]"
            continue
        data[key] = _redact_value(value, sensitive_keys)

    return data


def _default_timestamp() -> str:
    """Generate an ISO-8601 UTC timestamp string."""

    return datetime.now(timezone.utc).isoformat()


class RequestIdFilter(logging.Filter):
    """Attach request_id from context when absent on the record."""

    def filter(self, record: LogRecord) -> bool:  # noqa: D401
        if getattr(record, "request_id", None) is None:
            request_id = get_request_id()
            if request_id:
                record.request_id = request_id
        return True


class SensitiveDataFilter(logging.Filter):
    """Redact sensitive fields on the record before formatting."""

    def __init__(self, sensitive_keys: Iterable[str] | None = None) -> None:
        super().__init__()
        self.sensitive_keys = set(sensitive_keys or SENSITIVE_KEYS_DEFAULT)

    def filter(self, record: LogRecord) -> bool:  # noqa: D401
        sanitized = _sanitize_record(record, self.sensitive_keys)
        for key, value in sanitized.items():
            setattr(record, key, value)
        return True


class JsonFormatter(logging.Formatter):
    """Format LogRecord as JSON with redaction support."""

    def __init__(
        self,
        *,
        sensitive_keys: Iterable[str] | None = None,
        ensure_ascii: bool = True,
    ) -> None:
        super().__init__()
        self.sensitive_keys = set(sensitive_keys or SENSITIVE_KEYS_DEFAULT)
        self.ensure_ascii = ensure_ascii

    def format(self, record: LogRecord) -> str:  # noqa: D401
        record_data = {
            "timestamp": _default_timestamp(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None) or get_request_id()
        if request_id:
            record_data["request_id"] = request_id

        extras = _sanitize_record(record, self.sensitive_keys)
        record_data.update(extras)

        return json.dumps(record_data, default=str, ensure_ascii=self.ensure_ascii)


def _build_handler(log_settings: LogSettings) -> logging.Handler:
    """Construct the logging handler based on configuration.

    Args:
        log_settings: Resolved logging settings from environment.

    Returns:
        Configured logging handler (stdout or rotating file).
    """

    if log_settings.output.lower() == "file":
        file_path = Path(log_settings.file_path or "logs/app.log")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if log_settings.max_bytes:
            handler = RotatingFileHandler(
                file_path,
                maxBytes=log_settings.max_bytes,
                backupCount=log_settings.backup_count,
                encoding="utf-8",
            )
        else:
            handler = logging.FileHandler(file_path, encoding="utf-8")
        return handler

    return logging.StreamHandler(sys.stdout)


def configure_logging(log_settings: LogSettings | None = None) -> None:
    """Configure root logger with JSON formatter and redaction.

    Args:
        log_settings: Optional log settings; defaults to global settings if omitted.
    """

    cfg = log_settings or settings.log

    level = getattr(logging, cfg.level.upper(), logging.INFO)
    handler = _build_handler(cfg)

    handler.addFilter(RequestIdFilter())
    handler.addFilter(SensitiveDataFilter(SENSITIVE_KEYS_DEFAULT))

    if cfg.format.lower() == "plain":
        formatter: logging.Formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    else:
        formatter = JsonFormatter(sensitive_keys=SENSITIVE_KEYS_DEFAULT)

    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Avoid double logging from uvicorn if it gets re-configured
    logging.getLogger("uvicorn").propagate = False
    logging.getLogger("uvicorn.access").propagate = False
