import logging
import os
from typing import List

LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ENABLE_FILE_LOG = os.getenv("LOG_TO_FILE", "1").lower() not in ("0", "false", "no")

log_level = getattr(logging, LOG_LEVEL, logging.INFO)

handlers: List[logging.Handler] = [logging.StreamHandler()]

if ENABLE_FILE_LOG:
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        file_path = os.path.join(LOG_DIR, "pipeline.log")
        handlers.insert(0, logging.FileHandler(file_path, encoding="utf-8"))
    except Exception as e:  # PermissionError or others
        # Fallback: only stdout logging
        print(f"[logging] WARNING: file logging disabled ({e}). Using stdout only.")

logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=handlers,
)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)