import logging
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

LOG_FILE = BASE_DIR / "debug.log"

class UnbufferedFileHandler(logging.FileHandler):
    """FileHandler без буферизации: каждый emit сразу пишется на диск."""
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()
        os.fsync(self.stream.fileno())


logger = logging.getLogger("trading_app")
logger.setLevel(logging.DEBUG)

file_handler = UnbufferedFileHandler(LOG_FILE, mode="a", encoding="utf-8")
file_handler.setLevel(logging.INFO)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.WARNING)

formatter = logging.Formatter(
    fmt="%(asctime)s - %(levelname)s - %(name)s - "
        "%(filename)s:%(lineno)d - %(message)s"
)

file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)