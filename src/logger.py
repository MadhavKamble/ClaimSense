"""
Structured logging — replaces scattered print() statements with real,
timestamped, leveled logs written both to console and to a file.

Why this matters for an "automation"-flavored project specifically: a system
that's meant to run unattended (which is the whole point of hyperautomation)
needs to leave a trail of what it did and when, for debugging and audit —
print statements disappear the moment the terminal closes.
"""

import logging
from pathlib import Path

from config import CONFIG

LOGS_DIR = Path(__file__).parent.parent / CONFIG["paths"]["logs_dir"]
LOGS_DIR.mkdir(exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:  # avoid duplicate handlers if called multiple times
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(LOGS_DIR / "pipeline.log")
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
