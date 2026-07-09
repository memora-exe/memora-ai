import logging
import sys

# Memory bug fix: avoid noisy duplicate handlers on reload
_INITIALIZED = False

def setup_logging() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    # Root logger: INFO + format tương tự NestJS "[Nest] PID - timestamp LEVEL [context] message"
    handler = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
        datefmt="%m/%d/%Y, %I:%M:%S %p",
    )
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    _INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
