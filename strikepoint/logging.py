import logging
from queue import Queue
from sys import stdout


_FMT = "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# convenience module-level logger
# logging.basicConfig(level=logging.WARNING, format=_FMT, datefmt=_DATEFMT)
# logger = logging.getLogger("strikepoint")

# info = logger.info
# debug = logger.debug
# warning = logger.warning
# error = logger.error
# critical = logger.critical
# fatal = logger.fatal


class CaptureHandler(logging.Handler):
    def __init__(self, msgQueue: Queue):
        super().__init__()
        self.msgQueue = msgQueue
        self.setLevel(logging.DEBUG)
        self.setFormatter(logging.Formatter(fmt=_FMT, datefmt=_DATEFMT))

    def emit(self, record):
        message = self.format(record)
        self.msgQueue.put((record, message))


def setupLogging(*, level=logging.DEBUG, msgQueue: Queue = None):
    """Configure root logging for the application."""
    rootLogger = logging.getLogger()
    rootLogger.setLevel(level)

    # Remove any existing handlers (important in tests / reloads)
    rootLogger.handlers.clear()

    formatter = logging.Formatter(fmt=_FMT, datefmt=_DATEFMT)
    consoleHandler = logging.StreamHandler(stdout)
    consoleHandler.setFormatter(formatter)
    rootLogger.addHandler(consoleHandler)

    if msgQueue is not None:
        captureHandler = CaptureHandler(msgQueue)
        rootLogger.addHandler(captureHandler)

