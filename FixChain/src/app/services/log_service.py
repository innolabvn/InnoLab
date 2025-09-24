# core/logger.py
import logging
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

root_env_path = Path(__file__).resolve().parents[3] / '.env'
load_dotenv(root_env_path)

def setup_logger() -> logging.Logger:
    """Setup application logger with console + file handler."""
    
    # Use different log directory based on environment
    # Check if running in Docker container by checking current working directory
    current_dir = os.getcwd()
    if current_dir == "/app" or os.getenv("DOCKER_ENV"):
        # Running in Docker container
        log_dir = os.getenv("LOG_DIR", "logs")
    else:
        # Running outside Docker, use project root logs directory
        project_root = Path(__file__).resolve().parents[3]
        log_dir = os.getenv("LOG_DIR", str(project_root / "logs"))
    
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("FixChain")
    if logger.handlers:
        return logger  # tránh thêm handler lặp lại

    # Lấy level từ env, mặc định INFO
    level_name = os.getenv("LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    # Format log có timestamp, level, module
    log_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(module)s:%(lineno)d | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # File handler (optional, xoay file theo ngày)
    log_file = os.path.join(log_dir, f"fixchain_{datetime.now().strftime('%m%d%H')}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()
