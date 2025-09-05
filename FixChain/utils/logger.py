import logging
import os
from datetime import datetime

def setup_logger():
    """Setup logger configuration for the application."""
    # Create logs directory if it doesn't exist
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Create a logger
    logger = logging.getLogger('InnoLab')
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        console_handler = logging.StreamHandler()

        log_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(log_format)

        logger.addHandler(console_handler)

    return logger

logger = setup_logger()
