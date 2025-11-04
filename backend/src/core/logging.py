"""
Structured logging configuration with correlation IDs.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from backend.src.core.config import settings

# Context variable for request correlation ID
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging in JSON format."""

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as structured JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if available
        request_id = request_id_ctx.get()
        if request_id:
            log_data["request_id"] = request_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        # Add standard fields
        log_data.update(
            {
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }
        )

        if settings.LOG_FORMAT == "json":
            return json.dumps(log_data)
        else:
            # Text format for development
            request_id_str = f" [{request_id}]" if request_id else ""
            return (
                f"{log_data['timestamp']} - {record.levelname:8} - "
                f"{record.name}{request_id_str} - {record.getMessage()}"
            )


def setup_logging() -> None:
    """Configure application logging."""
    # Remove existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(StructuredFormatter())

    # Configure root logger
    root_logger.addHandler(console_handler)
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def set_request_id(request_id: Optional[str] = None) -> str:
    """
    Set correlation ID for current request context.

    Args:
        request_id: Request ID to set, or None to generate new one

    Returns:
        The request ID that was set
    """
    if request_id is None:
        request_id = str(uuid4())
    request_id_ctx.set(request_id)
    return request_id


def get_request_id() -> Optional[str]:
    """
    Get correlation ID for current request context.

    Returns:
        Current request ID or None
    """
    return request_id_ctx.get()


def clear_request_id() -> None:
    """Clear correlation ID from current request context."""
    request_id_ctx.set(None)


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    **kwargs: Any,
) -> None:
    """
    Log a message with additional context.

    Args:
        logger: Logger instance
        level: Log level
        message: Log message
        **kwargs: Additional context to include in log
    """
    extra = {"extra": kwargs} if kwargs else {}
    logger.log(level, message, extra=extra)


# Initialize logging on module import
setup_logging()
