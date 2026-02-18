"""Structured logging for quota management."""

import json
import logging
import sys
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Add context fields if present
        if hasattr(record, "instance"):
            log_data["instance"] = record.instance
        if hasattr(record, "cluster"):
            log_data["cluster"] = record.cluster
        if hasattr(record, "project"):
            log_data["project"] = record.project
        if hasattr(record, "namespace"):
            log_data["namespace"] = record.namespace

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class ContextLogger:
    """Logger with context injection."""

    def __init__(self, logger: logging.Logger):
        """Initialize context logger."""
        self.logger = logger
        self.context: Dict[str, Optional[str]] = {
            "instance": None,
            "cluster": None,
            "project": None,
            "namespace": None,
        }

    def set_context(
        self,
        instance: Optional[str] = None,
        cluster: Optional[str] = None,
        project: Optional[str] = None,
        namespace: Optional[str] = None,
    ) -> None:
        """Set logging context."""
        if instance is not None:
            self.context["instance"] = instance
        if cluster is not None:
            self.context["cluster"] = cluster
        if project is not None:
            self.context["project"] = project
        if namespace is not None:
            self.context["namespace"] = namespace

    def _log(
        self, level: int, msg: str, *args: Any, **kwargs: Any
    ) -> None:
        """Log with context."""
        extra = kwargs.get("extra", {})
        extra.update(self.context)
        kwargs["extra"] = extra
        self.logger.log(level, msg, *args, **kwargs)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log info message."""
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log warning message."""
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log error message."""
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log critical message."""
        self._log(logging.CRITICAL, msg, *args, **kwargs)


def setup_logging(level: str = "INFO") -> ContextLogger:
    """Set up structured logging."""
    logger = logging.getLogger("quotactl")
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Add console handler with JSON formatter
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)

    return ContextLogger(logger)


def mask_secret(value: str) -> str:
    """Mask secret value in logs."""
    if not value or len(value) < 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"

