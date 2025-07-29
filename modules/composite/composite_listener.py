# import asyncio
# import datetime as dt
# from typing import Dict, List, Set

# from .ast_transform import Cooldown, Expr
# from .plan import compile_plan, PlanFn
# from .registry import create_listener
# from .utils import collect_conditions
# from ..listener import Listener

# TickerSet = Set[str]


# class CompositeListener(Listener):
#     """Слушатель, срабатывающий на логическую комбинацию под‑слушателей."""

#     def __init__(self, expr: Expr, user_id: int) -> None:
#         """
#         Args:
#             expr: Корневой узел AST (возможно, Cooldown).
#             user_id: ID владельца алерта (Telegram).
#         """
#         super().__init__()
#         self.user_id = user_id

#         if isinstance(expr, Cooldown):
#             self._cooldown = expr.cooldown
#             self._root: Expr = expr.expr
#         else:
#             self._cooldown = 0
#             self._root = expr

#         self._plan: PlanFn = compile_plan(self._root)
#         self._leaf_conditions = list(collect_conditions(self._root))
#         self._leaf_listeners: List[Listener] = []

#         self._last_fired: Dict[str, dt.datetime] = {}

#     async def start(self) -> None:
#         """Создаёт/запускает дочерние слушатели; вызывается один раз."""
#         if self._leaf_listeners:
#             return
#         for cond in self._leaf_conditions:
#             lst = await create_listener(cond, self.user_id)
#             self._leaf_listeners.append(lst)
#             await lst.start()
#         self._period = min(lst.period_sec for lst in self._leaf_listeners)
#         self._next_check = dt.datetime.utcnow()

#     async def maybe_update(self) -> None:
#         """Обновляется и рассылает алерты, только если подошло время."""
#         now = dt.datetime.utcnow()
#         if now < self._next_check:
#             return

#         await self.update_state()
#         await self.notify()
#         self._next_check = now + dt.timedelta(seconds=self._period)

#     async def update_state(self) -> None:
#         """Обновляет дочерних и вычисляет итоговый matched set."""
#         await asyncio.gather(*(lst.update_state() for lst in self._leaf_listeners))

#         context = {
#             cond.module: lst.matched_symbol_only()
#             for cond, lst in zip(self._leaf_conditions, self._leaf_listeners)
#         }
#         triggered: TickerSet = self._plan(context)

#         if self._cooldown:
#             now = dt.datetime.utcnow()
#             triggered = {
#                 t for t in triggered
#                 if now - self._last_fired.get(t, dt.datetime.min)
#                 >= dt.timedelta(seconds=self._cooldown)
#             }
#             for t in triggered:
#                 self._last_fired[t] = now

#         self._matched = triggered

#     async def notify(self) -> None:
#         """Шлёт уведомления подписчикам по каждому сработавшему тикеру."""
#         if not self._matched:
#             return
#         msg = (
#             "⚡️ Композитный алерт\n"
#             f"Тикеры: {', '.join(sorted(self._matched))}\n"
#             f"Условие: {self._root}"
#         )
#         await self.notify_subscribers(msg)

import asyncio, datetime as dt, uuid
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
    Не наследует базовый Listener — держит собственный state/subscribers.
    """

    def __init__(self, expr: Expr, owner: int) -> None:
        self.id: str = f"cmp-{uuid.uuid4()}"   # уникальный ID
        self.owner = owner                     # владелец (Telegram ID)
        self.subscribers: set[int] = {owner}

        # --- разбор AST и компиляция плана ---
        if isinstance(expr, Cooldown):
            self._cooldown = expr.seconds
            self._root = expr.expr
        else:
            self._cooldown = 0
            self._root = expr

        self._plan: PlanFn = compile_plan(self._root)
        self._leaf_conditions = list(collect_conditions(self._root))
        self._leaf_listeners: List["Listener"] = []   # позже заполним

        self._matched: TickerSet = set()
        self._last_fired: Dict[str, dt.datetime] = {}
        self._period: int = 1                         # пересчитаем в start()
        self._next_check: dt.datetime | None = None

    # ---------- публичный API ---------- #

    async def start(self) -> None:
        """Создаёт дочерние слушатели и высчитывает минимальный period."""
        if self._leaf_listeners:
            return

        for cond in self._leaf_conditions:
            lst = await create_listener(cond, self.owner)
            self._leaf_listeners.append(lst)
            # Manager уже запустил атомарный Listener, поэтому .start() не нужен.

        # берём period_sec, если модуль его реализует, иначе дефолт 60 с
        self._period = min(
            getattr(lst, "period_sec", 60) for lst in self._leaf_listeners
        )
        self._next_check = dt.datetime.utcnow()

    async def maybe_update(self) -> None:
        """Периодически вызывается менеджером, выполняет проверку алерта.

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
        self.subscribers.add(uid)

    async def _notify(self) -> None:
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

    # ---------- вспомогательное ---------- #
    @property
    def period_sec(self) -> int:
        return self._period

    def matched_symbol_only(self) -> TickerSet:
        """Совместимость с Composite‑планом (для вложенных структур)."""
        return self._matched
