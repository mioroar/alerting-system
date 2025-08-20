import asyncpg
from typing import Tuple

from modules.listener import Listener


class OrderListener(Listener):
    """Слушатель плотности ордеров.
    
    Отслеживает крупные ордера в стакане, которые держатся определенное время
    на определенном расстоянии от текущей цены.
    """

    def __init__(
        self,
        condition_id: str,
        direction: str,
        percent: float,
        interval: int,
        window_sec: int | None = None,
    ) -> None:
        """Инициализирует слушатель ордеров.

        Args:
            condition_id: Уникальный идентификатор условия.
            direction: Направление сравнения ('>' или '<').
            percent: Размер ордера в USD (используется как временное значение).
            interval: Интервал проверки в секундах.
            window_sec: Длина окна расчёта в секундах.
        """
        super().__init__(condition_id, direction, percent, interval, window_sec)
        self.matched: list[Tuple[str, float, float, int]] = []
        
        # Специфичные параметры для order
        self.size_usd: float = 1000000.0
        self.max_percent: float = 5.0
        self.min_duration: int = 300

    @property
    def period_sec(self) -> int:
        """Возвращает интервал между обновлениями состояния."""
        return self.interval

    def set_order_params(
        self, 
        size_usd: float, 
        max_percent: float, 
        min_duration: int
    ) -> None:
        """Устанавливает специфичные параметры для order-слушателя.

        Args:
            size_usd: Минимальный размер ордера в USD.
            max_percent: Максимальное отклонение от текущей цены (%).
            min_duration: Минимальное время жизни ордера в секундах.
        """
        self.size_usd = size_usd
        self.max_percent = max_percent
        self.min_duration = min_duration

    async def update_state(self, db_pool: asyncpg.Pool) -> None:
        """Обновляет состояние слушателя данными о плотности ордеров.

        Выполняет SQL-запрос для получения крупных ордеров, которые держатся
        достаточно долго в пределах заданного отклонения от текущей цены.

        Args:
            db_pool: Пул соединений с базой данных.
        """
        self.matched.clear()
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT symbol, 
                       order_type,
                       size_usd,
                       duration_sec,
                       percent_from_market
                FROM order_density 
                WHERE size_usd >= $1 
                  AND ABS(percent_from_market) <= $2
                  AND duration_sec >= $3
                  AND ts >= NOW() - INTERVAL '1 hour'
                ORDER BY size_usd DESC
                """,
                self.size_usd,
                self.max_percent,
                self.min_duration,
            )
        
        for row in rows:
            if self._trigger(row["size_usd"], row["duration_sec"]):
                self.matched.append((
                    row["symbol"],
                    float(row["size_usd"]),
                    float(row["percent_from_market"]),
                    int(row["duration_sec"])
                ))

    async def notify(self) -> None:
        """Отправляет уведомления подписчикам о найденных крупных ордерах.

        Формирует текстовые сообщения для каждого найденного ордера
        и отправляет их всем подписчикам.
        """
        if not self.subscribers or not self.matched:
            return
        
        for symbol, size_usd, percent_from_market, duration_sec in self.matched:
            direction_text = "выше" if percent_from_market > 0 else "ниже"
            size_formatted = self._format_usd(size_usd)
            duration_formatted = self._format_duration(duration_sec)
            
            text = (
                f"[ORDER] {symbol}: крупный ордер {size_formatted} "
                f"({abs(percent_from_market):.2f}% {direction_text} цены) "
                f"держится {duration_formatted}"
            )
            await self._notify_subscribers(text)

    def _trigger(self, size_usd: float, duration_sec: int) -> bool:
        """Проверяет условие срабатывания на основе размера и времени жизни ордера.

        Args:
            size_usd: Размер ордера в USD.
            duration_sec: Время жизни ордера в секундах.

        Returns:
            True если условие сработало, False в противном случае.
        """
        if self.direction == ">":
            return size_usd >= self.size_usd and duration_sec >= self.min_duration
        elif self.direction == "<":
            return size_usd <= self.size_usd and duration_sec >= self.min_duration
        return False

    def _format_usd(self, value: float) -> str:
        """Форматирует сумму в USD в человекочитаемый вид.

        Args:
            value: Сумма в USD.

        Returns:
            Отформатированная строка с суффиксом.
        """
        if value >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        elif value >= 1_000:
            return f"${value / 1_000:.1f}K"
        else:
            return f"${value:.0f}"

    def _format_duration(self, seconds: int) -> str:
        """Форматирует время в секундах в человекочитаемый вид.

        Args:
            seconds: Время в секундах.

        Returns:
            Отформатированная строка времени.
        """
        if seconds >= 3600:
            hours = seconds // 3600
            return f"{hours}ч"
        elif seconds >= 60:
            minutes = seconds // 60
            return f"{minutes}мин"
        else:
            return f"{seconds}сек"

    async def _notify_subscribers(self, text: str) -> None:
        """Временная реализация уведомлений подписчиков.

        Args:
            text: Текст уведомления для отправки.
        """
        # Временная реализация - просто выводим в консоль
        # В будущем должна использоваться реализация из базового класса
        for user_id in self.subscribers:
            print(f"Alert for user {user_id}: {text}")