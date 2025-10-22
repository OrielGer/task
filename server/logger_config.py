"""
Server Logging Configuration
Sets up dual logging (console + file) with timestamps
"""

import logging
import sys
from common.config import LOG_FILE, LOG_LEVEL_CONSOLE, LOG_LEVEL_FILE


def setup_logging():
    """
    Configure logging to both console and file with timestamps

    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger('C2Server')
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers to avoid duplicates
    logger.handlers = []

    # Console handler - INFO level (Level 2 requirement)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LOG_LEVEL_CONSOLE))
    console_format = logging.Formatter('[%(levelname)s] %(message)s')
    console_handler.setFormatter(console_format)

    # File handler - DEBUG level with timestamps
    file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    file_handler.setLevel(getattr(logging, LOG_LEVEL_FILE))
    file_format = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)

    # Add both handlers (Level 2: log to console AND file)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# Create global logger instance
logger = setup_logging()
