"""Centralized file-based logging for the API.

Log files are rotated daily and stored in logs/serp_api/
"""

import logging
import sys
import threading
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

# Global logging state
_loggers_initialized = False
_loggers_lock = threading.Lock()


class LogFormatter(logging.Formatter):
    """Custom formatter with timestamp and structured format."""

    def __init__(self, fmt: Optional[str] = None):
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S.%f",
        )

    def format(self, record: logging.LogRecord) -> str:
        # Remove microseconds from timestamp for cleaner output
        record.asctime = datetime.fromtimestamp(record.created).strftime(
            "%Y-%m-%d %H:%M:%S.%f"[:-3]
        )
        return super().format(record)


def setup_logging(
    log_dir: Path,
    log_level: str = "INFO",
) -> None:
    """Set up centralized logging for the API and serp library.

    Creates multiple log files:
    - api.log: General application logs
    - access.log: All HTTP requests
    - error.log: ERROR and CRITICAL only
    - search.log: Search endpoint logs
    - serp.client: SERP library logs

    Args:
        log_dir: Directory to store log files
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    global _loggers_initialized

    with _loggers_lock:
        if _loggers_initialized:
            return

        log_dir = Path(log_dir) / "serp_api"
        log_dir.mkdir(parents=True, exist_ok=True)

        level = getattr(logging, log_level.upper(), logging.INFO)

        # Create formatters
        formatter = LogFormatter()
        detailed_formatter = LogFormatter()

        # Logger configurations
        logger_configs = [
            ("api", log_dir / "api.log", level, formatter),
            ("api.access", log_dir / "access.log", level, formatter),
            ("api.error", log_dir / "error.log", logging.ERROR, formatter),
            ("api.routers.search", log_dir / "search.log", level, detailed_formatter),
            ("api.routers.fetch", log_dir / "fetch.log", level, detailed_formatter),
            ("api.routers.news", log_dir / "news.log", level, detailed_formatter),
            # SERP library loggers
            ("serp", log_dir / "serp.log", level, formatter),
            ("serp.client", log_dir / "serp_client.log", level, detailed_formatter),
        ]

        for logger_name, log_file, logger_level, log_formatter in logger_configs:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logger_level)

            # Avoid duplicate handlers
            if logger.handlers:
                continue

            # File handler with daily rotation
            file_handler = TimedRotatingFileHandler(
                log_file,
                when="midnight",
                interval=1,
                backupCount=7,  # Keep 7 days of logs
                encoding="utf-8",
            )
            file_handler.setLevel(logger_level)
            file_handler.setFormatter(log_formatter)
            logger.addHandler(file_handler)

        # Also log to stdout in debug mode
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG if log_level == "DEBUG" else logging.INFO)
        console_handler.setFormatter(LogFormatter())
        logging.getLogger("api").addHandler(console_handler)

        _loggers_initialized = True


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name (e.g., "api.routers.search")

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
