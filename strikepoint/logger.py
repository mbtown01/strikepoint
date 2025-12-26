import logging
import sys
from typing import Optional


# Module logger name used by the package
LOGGER_NAME = "strikepoint"

# Format matching driver.c's _driverLog:
#   "YYYY-MM-DD HH:MM:SS [LEVEL] filename:lineno - message"
_FMT = "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _make_formatter() -> logging.Formatter:
    return logging.Formatter(fmt=_FMT, datefmt=_DATEFMT)


def get_logger(name: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger for the package.

    - name: optional child logger name (e.g. 'strikepoint.driver').
    - level: default logging level.
    """
    root_name = LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}"
    logger = logging.getLogger(root_name)
    logger.setLevel(level)
    logger.propagate = False  # we manage handlers explicitly

    # Add a single stdout handler if none present
    if not any(isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
               for h in logger.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(level)
        sh.setFormatter(_make_formatter())
        logger.addHandler(sh)

    return logger


def set_log_level(level: int):
    """Set level on package logger and its handlers."""
    logger = get_logger()
    logger.setLevel(level)
    for h in logger.handlers:
        h.setLevel(level)


def set_log_file(path: str, level: int = logging.DEBUG):
    """Add or replace a file handler that writes using the package format."""
    logger = get_logger()
    # remove existing FileHandler instances first
    for h in list(logger.handlers):
        if isinstance(h, logging.FileHandler):
            logger.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass

    fh = logging.FileHandler(path, mode="a")
    fh.setLevel(level)
    fh.setFormatter(_make_formatter())
    logger.addHandler(fh)


# convenience module-level logger
logger = get_logger()
