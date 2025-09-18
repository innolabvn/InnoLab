# core/logger.py
import logging
import os
from datetime import datetime

def setup_logger() -> logging.Logger:
    """Setup application logger with console + file handler."""
    # Sử dụng đường dẫn tương đối từ thư mục hiện tại
    log_dir = os.getenv("LOG_DIR", "logs")
    # Tạo đường dẫn tuyệt đối từ thư mục gốc của project
    if not os.path.isabs(log_dir):
        # Lấy thư mục gốc của project (3 level up từ file này)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
        log_dir = os.path.join(project_root, log_dir)
    
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        # Nếu không tạo được thư mục logs, sử dụng /tmp
        log_dir = "/tmp/fixchain_logs"
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
        "%(asctime)s | %(levelname)-8s | %(name)s | %(module)s:%(lineno)d | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # File handler (optional, xoay file theo ngày)
    log_file = os.path.join(log_dir, f"fixchain_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()
