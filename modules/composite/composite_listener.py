import datetime as dt
from typing import Dict, List, Set

from bot.settings import bot
from modules.listener import Listener
from .ast_transform import Cooldown, Expr
from .plan import compile_plan, PlanFn
from .registry import create_listener
from modules.composite.utils import collect_conditions, ast_to_string

TickerSet = Set[str]


class CompositeListener:
    """
    Логическая обёртка над набором Listener‑ов.

    Attributes:
        id (str): Уникальный идентификатор композитного слушателя.
        owner (int): ID владельца слушателя.
        subscribers (set[int]): Множество ID подписчиков.
        _cooldown (int): Время задержки между срабатываниями алерта.
        _root (Expr): Корневое выражение AST.
        _plan (PlanFn): Скомпилированный логический план.
        _leaf_conditions (list): Листовые условия AST.
        _leaf_listeners (List[Listener]): Список дочерних слушателей.
        _matched (TickerSet): Совпавшие тикеры.
        _last_fired (Dict[str, dt.datetime]): Время последнего срабатывания по тикеру.
        _period (int): Минимальный период проверки в секундах.
        _next_check (dt.datetime | None): Время следующей проверки.
    """

    def __init__(self, expr: Expr, owner: int, listener_id: str) -> None:
        """
        Инициализация CompositeListener.

        Args:
            expr (Expr): AST выражение условия алерта.
            owner (int): ID владельца слушателя.
            listener_id (str): Уникальный ID слушателя.
        """
        self.id: str = listener_id
        self.owner = owner
        self.subscribers: set[int] = {owner}

        if isinstance(expr, Cooldown):
            self._cooldown = expr.seconds
            self._root = expr.expr
        else:
            self._cooldown = 0
            self._root = expr

        self._plan: PlanFn = compile_plan(self._root)
        self._leaf_conditions = list(collect_conditions(self._root))
        self._leaf_listeners: List["Listener"] = []

        self._matched: TickerSet = set()
        self._last_fired: Dict[str, dt.datetime] = {}
        self._period: int = 1
        self._next_check: dt.datetime | None = None

    async def start(self) -> None:
        """
        Создаёт дочерние слушатели и высчитывает минимальный period.

        Returns:
            None
        """
        if self._leaf_listeners:
            return

        for cond in self._leaf_conditions:
            lst = await create_listener(cond, self.owner)
            self._leaf_listeners.append(lst)

        self._period = min(
            getattr(lst, "period_sec", 60) for lst in self._leaf_listeners
        )
        self._next_check = dt.datetime.utcnow()

    async def maybe_update(self) -> None:
        """
        Периодически вызывается менеджером, выполняет проверку алерта.

        Returns:
            None

        Логи:
            [CTX mod]  – список тикеров от каждого датчика;
            [TRG raw]  – результат логического плана ДО cooldown;
            [TRG cool] – итог после фильтра cooldown;
            [SUBS]     – список подписчиков;
            [SEND ERR] – ошибки отправки сообщений в Telegram.
        """
        now = dt.datetime.utcnow()
        if now < self._next_check:
            return

        try:
            context = {}
            for cond, lst in zip(self._leaf_conditions, self._leaf_listeners):
                try:
                    tickers = lst.matched_symbol_only()
                    context[cond.module] = tickers
                    print(f"[CTX {cond.module:7}] {sorted(tickers)}")
                except Exception as exc:
                    print(f"[CTX ERROR {cond.module}] {exc}")
                    context[cond.module] = set()

            triggered: Set[str] = self._plan(context)
            print("[TRG raw ]", sorted(triggered))

            if self._cooldown:
                cooldown_filtered = set()
                for ticker in triggered:
                    last_fired = self._last_fired.get(ticker, dt.datetime.min)
                    if now - last_fired >= dt.timedelta(seconds=self._cooldown):
                        cooldown_filtered.add(ticker)
                        self._last_fired[ticker] = now
                
                triggered = cooldown_filtered
                print("[TRG cool]", sorted(triggered))

            self._matched = triggered

            if self._matched:
                await self._send_notifications()

        except Exception as exc:
            print(f"[UPDATE ERROR] {self.id}: {exc}")
        finally:
            self._next_check = now + dt.timedelta(seconds=self._period)

    async def _send_notifications(self) -> None:
        """
        Отправляет уведомления всем подписчикам.

        Returns:
            None
        """
        msg = (
            "⚡️ Композитный алерт\n"
            f"Тикеры: {', '.join(sorted(self._matched))}\n"
            f"Условие: {ast_to_string(self._root)}"
        )
        print("[SUBS]", self.subscribers)
        
        for user_id in self.subscribers:
            try:
                await bot.send_message(user_id, msg)
            except Exception as exc:
                print("[SEND ERR]", user_id, exc)

    def add_subscriber(self, user_id: int) -> None:
        """
        Добавляет подписчика на алерт.

        Args:
            user_id (int): ID пользователя.
        """
        self.subscribers.add(user_id)

    def remove_subscriber(self, user_id: int) -> None:
        """
        Удаляет подписчика из алерта.
        """
        self.subscribers.remove(user_id)

    @property
    def period_sec(self) -> int:
        """
        Минимальный период проверки в секундах.

        Returns:
            int: Период проверки.
        """
        return self._period

    def matched_symbol_only(self) -> TickerSet:
        """
        Совместимость с Composite‑планом (для вложенных структур).

        Returns:
            TickerSet: Совпавшие тикеры.
        """
        return self._matched

    async def stop(self) -> None:
        """
        Останавливает композитный слушатель и освобождает ресурсы.

        Останавливает все дочерние слушатели и очищает внутренние данные.

        Returns:
            None
        """
        for leaf_listener in self._leaf_listeners:
            try:
                await leaf_listener.stop()
            except Exception as exc:
                print(f"[COMPOSITE] Ошибка при остановке дочернего слушателя: {exc}")
        
        self._leaf_listeners.clear()
        self.subscribers.clear()
        self._matched.clear()
        self._last_fired.clear()