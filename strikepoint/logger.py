import logging
import sys
from typing import Optional


# Module logger name used by the package
LOGGER_NAME = "strikepoint"

# Format matching driver.c's _driverLog:
#   "YYYY-MM-DD HH:MM:SS [LEVEL] filename:lineno - message"
_FMT = "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _makeFormatter() -> logging.Formatter:
    return logging.Formatter(fmt=_FMT, datefmt=_DATEFMT)


def _getLogger(level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger for the package.

    - name: optional child logger name (e.g. 'strikepoint.driver').
    - level: default logging level.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False  # we manage handlers explicitly

    # Add a single stdout handler if none present
    if not any(isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
               for h in logger.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(level)
        sh.setFormatter(_makeFormatter())
        logger.addHandler(sh)

    return logger


# def set_log_level(level: int):
#     """Set level on package logger and its handlers."""
#     logger = _getLogger()
#     logger.setLevel(level)
#     for h in logger.handlers:
#         h.setLevel(level)


# def set_log_file(path: str, level: int = logging.DEBUG):
#     """Add or replace a file handler that writes using the package format."""
#     logger = get_logger()
#     # remove existing FileHandler instances first
#     for h in list(logger.handlers):
#         if isinstance(h, logging.FileHandler):
#             logger.removeHandler(h)
#             try:
#                 h.close()
#             except Exception:
#                 pass

#     fh = logging.FileHandler(path, mode="a")
#     fh.setLevel(level)
#     fh.setFormatter(_make_formatter())
#     logger.addHandler(fh)


# convenience module-level logger
logger = _getLogger()
info = logger.info
debug = logger.debug
warning = logger.warning
error = logger.error
critical = logger.critical
fatal = logger.fatal
