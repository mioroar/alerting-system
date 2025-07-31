import datetime as dt, uuid
from typing import Dict, List, Set

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

    def __init__(self, expr: Expr, owner: int) -> None:
        """
        Инициализация CompositeListener.

        Args:
            expr (Expr): AST выражение условия алерта.
            owner (int): ID владельца слушателя.
        """
        self.id: str = f"cmp-{uuid.uuid4()}"
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

        context = {
            cond.module: lst.matched_symbol_only()
            for cond, lst in zip(self._leaf_conditions, self._leaf_listeners)
        }

        for mod, tickers in context.items():
            print(f"[CTX {mod:7}] {sorted(tickers)}")

        triggered: Set[str] = self._plan(context)
        print("[TRG raw ]", sorted(triggered))

        if self._cooldown:
            triggered = {
                t for t in triggered
                if now - self._last_fired.get(t, dt.datetime.min)
                >= dt.timedelta(seconds=self._cooldown)
            }
            print("[TRG cool]", sorted(triggered))
            for t in triggered:
                self._last_fired[t] = now

        self._matched = triggered


        if self._matched:
            from bot.settings import bot
            msg = (
                "⚡️ Композитный алерт\n"
                f"Тикеры: {', '.join(sorted(self._matched))}\n"
                f"Условие: {ast_to_string(self._root)}"
            )
            print("[SUBS]", self.subscribers)
            for uid in self.subscribers:
                try:
                    await bot.send_message(uid, msg)
                except Exception as exc:
                    print("[SEND ERR]", uid, exc)

        self._next_check = now + dt.timedelta(seconds=self._period)

    def add_subscriber(self, uid: int) -> None:
        """
        Добавляет подписчика на алерт.

        Args:
            uid (int): ID пользователя.
        """
        self.subscribers.add(uid)

    async def _notify(self) -> None:
        """
        Отправляет уведомление всем подписчикам, если есть совпадения.

        Returns:
            None
        """
        if not self._matched:
            return
        from bot.settings import bot
        msg = (
            "⚡️ Композитный алерт\n"
            f"Тикеры: {', '.join(sorted(self._matched))}\n"
            f"Условие: {self._root}"
        )
        for uid in self.subscribers:
            await bot.send_message(uid, msg)

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
