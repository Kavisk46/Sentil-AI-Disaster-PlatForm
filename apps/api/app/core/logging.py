"""Logging configuration.

Uses the standard library's logging module with a single, explicit
dictConfig so log format and verbosity are consistent across every module
and are controlled entirely by the `LOG_LEVEL` setting, rather than each
module configuring its own logger ad hoc.
"""

import logging
import logging.config

from app.core.config import Settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def configure_logging(settings: Settings) -> None:
    """Configure the root logger. Call once, on application startup."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": LOG_FORMAT,
                    "datefmt": DATE_FORMAT,
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "handlers": ["console"],
                "level": settings.LOG_LEVEL,
            },
            "loggers": {
                # Quiet down noisy access logs at DEBUG; keep them at INFO.
                "uvicorn.access": {"level": "INFO", "propagate": True},
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
