import logging
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

LOG_FILE = BASE_DIR / "debug.log"

class UnbufferedFileHandler(logging.FileHandler):
    """FileHandler без буферизации: каждый emit сразу пишется на диск.
    
    Этот класс наследует от logging.FileHandler и переопределяет метод emit
    для обеспечения немедленной записи логов на диск без буферизации.
    Это полезно для отладки и мониторинга в реальном времени.
    """
    
    def emit(self, record: logging.LogRecord) -> None:
        """Записывает лог-запись на диск немедленно.
        
        Переопределяет стандартный метод emit для принудительной записи
        каждого лог-сообщения на диск без буферизации.
        
        Args:
            record: Лог-запись для записи в файл.
            
        Returns:
            None
        """
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