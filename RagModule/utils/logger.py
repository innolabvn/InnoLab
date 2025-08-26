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
    logger = logging.getLogger('innolab')
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        console_handler = logging.StreamHandler()
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        file_handler = logging.FileHandler(f'logs/innolab_{timestamp}.log')

        log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(log_format)
        file_handler.setFormatter(log_format)

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger

logger = setup_logger()
