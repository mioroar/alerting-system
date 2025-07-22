import time
import asyncpg
import importlib
from dataclasses import dataclass, field
from typing import Protocol, Set, Sequence, TypeVar, Generic, Optional, ClassVar

class EvalCtx(Protocol):
    """Контекст выполнения для одного прохода вычисления AST.

    В данный момент только проксирует пул БД, но использование Protocol позволяет
    легко расширять функционал в будущем (например, добавление кэшей в памяти или дополнительных сервисов).

    Атрибуты:
        db_pool (asyncpg.Pool): Пул соединений с базой данных.
    """

    db_pool: asyncpg.Pool


COND_REGISTRY: dict[str, type["_ListenerCond"]] = {}

def register_cond(tag: str):
    """Декоратор: кладёт класс Cond в реестр, чтобы ast_transform знал, какой узел создавать."""
    def _wrap(cls):
        COND_REGISTRY[tag] = cls
        return cls
    return _wrap


class Listener(Protocol):
    """Минимальный набор требований к реализации Listener.

    Атрибуты:
        matched (list[tuple[str, float]]): Список совпавших тикеров и значений.
        interval (int): Интервал опроса в секундах.
    """

    matched: list[tuple[str, float]]
    interval: int


class Node:
    """Базовый класс для всех AST-узлов (логических и листовых).

    Атрибуты:
        cooldown_sec (int): Кулдаун на тикер в секундах (0 - отключено).
    """

    cooldown_sec: int = 0
    _last_ts: dict[str, float] = field(default_factory=dict, init=False)


    async def eval(self, ctx: EvalCtx) -> Set[str]:
        """Вернуть множество тикеров, удовлетворяющих условию узла.

        Подклассы должны реализовать основную логику. Этот враппер только
        применяет кулдаун через :meth:`_apply_cd`.

        Args:
            ctx (EvalCtx): Контекст выполнения.

        Returns:
            Set[str]: Множество тикеров, прошедших условие.
        """

        raise NotImplementedError

    def _apply_cd(self, tickers: Set[str]) -> Set[str]:
        """Фильтрует тикеры по кулдауну, обновляя внутреннюю карту временных меток.

        Args:
            tickers (Set[str]): Множество тикеров для фильтрации.

        Returns:
            Set[str]: Тикеры, не находящиеся на кулдауне.
        """

        if self.cooldown_sec == 0:
            return tickers

        last = self.__dict__.setdefault("_last_ts", {})

        now = time.time()
        result = {t for t in tickers if now - last.get(t, 0.0) >= self.cooldown_sec}
        for t in result:
            last[t] = now
        return result

    def intervals(self) -> Sequence[int]:
        """Вернуть все интервалы опроса, содержащиеся в этом поддереве.

        Returns:
            Sequence[int]: Список интервалов опроса.
        """

        return []


@dataclass(slots=True)
class AndNode(Node):
    """Конъюнкция (A & B).

    Атрибуты:
        left (Node): Левый подузел.
        right (Node): Правый подузел.
    """

    left: Node
    right: Node

    async def eval(self, ctx: EvalCtx) -> Set[str]:
        """Вычисляет пересечение результатов двух подузлов с учетом кулдауна.

        Args:
            ctx (EvalCtx): Контекст выполнения.

        Returns:
            Set[str]: Тикеры, удовлетворяющие обоим условиям.
        """
        return self._apply_cd(await self.left.eval(ctx) & await self.right.eval(ctx))

    def intervals(self) -> Sequence[int]:
        """Возвращает интервалы опроса из обоих подузлов.

        Returns:
            Sequence[int]: Список интервалов.
        """
        return (*self.left.intervals(), *self.right.intervals())


@dataclass(slots=True)
class OrNode(Node):
    """Дизъюнкция (A | B).

    Атрибуты:
        left (Node): Левый подузел.
        right (Node): Правый подузел.
    """

    left: Node
    right: Node

    async def eval(self, ctx: EvalCtx) -> Set[str]:
        """Вычисляет объединение результатов двух подузлов с учетом кулдауна.

        Args:
            ctx (EvalCtx): Контекст выполнения.

        Returns:
            Set[str]: Тикеры, удовлетворяющие хотя бы одному условию.
        """
        return self._apply_cd(await self.left.eval(ctx) | await self.right.eval(ctx))

    def intervals(self) -> Sequence[int]:
        """Возвращает интервалы опроса из обоих подузлов.

        Returns:
            Sequence[int]: Список интервалов.
        """
        return (*self.left.intervals(), *self.right.intervals())


_Lis = TypeVar("_Lis", bound=Listener)


@dataclass(slots=True)
class _ListenerCond(Node, Generic[_Lis]):
    """Листовой узел, который лениво получает Listener через Manager.

    Атрибуты:
        direction (str): Направление сравнения ('>' или '<').
        interval (int): Интервал окна в секундах.
        _listener (Optional[_Lis]): Кэшированный Listener.
        _cache (Set[str]): Кэш тикеров, удовлетворяющих условию.
    """
    MANAGER_FQN: ClassVar[str]
    direction: str
    interval: int
    _listener: Optional[_Lis] = field(default=None, init=False, repr=False)
    _cache: Set[str] = field(default_factory=set, init=False, repr=False)


    async def _ensure_listener(self) -> _Lis:
        if self._listener:
            return self._listener

        if not getattr(self, "MANAGER_FQN", None):
            raise NotImplementedError("Set MANAGER_FQN in Cond class")

        module_path, factory = self.MANAGER_FQN.rsplit(".", 1)
        mgr_mod = importlib.import_module(module_path)
        get_mgr = getattr(mgr_mod, factory)
        mgr = await get_mgr()

        # параметры = все public‑поля dataclass
        params = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        self._listener = await mgr.add_listener(params, user_id=0)
        return self._listener

    async def eval(self, ctx: EvalCtx) -> Set[str]:
        """Вычисляет и кэширует тикеры, удовлетворяющие условию Listener.

        Args:
            ctx (EvalCtx): Контекст выполнения.

        Returns:
            Set[str]: Тикеры, удовлетворяющие условию.
        """
        if self._cache:
            return self._cache

        listener = await self._ensure_listener()
        ok = {sym for sym, _ in listener.matched}
        self._cache = self._apply_cd(ok)
        return self._cache

    def intervals(self) -> Sequence[int]:
        """Возвращает интервал опроса для данного Listener.

        Returns:
            Sequence[int]: Список из одного интервала.
        """
        return [self.interval]

@register_cond("price")
@dataclass(slots=True)
class _PriceCond(_ListenerCond[Listener]):
    percent: float
    MANAGER_FQN = "modules.price.manager.get_price_listener_manager"

@register_cond("volume")
@dataclass(slots=True)
class _VolumeCond(_ListenerCond[Listener]):
    amount: int
    MANAGER_FQN = "modules.volume.manager.get_volume_listener_manager"

@register_cond("volume_change")
@dataclass(slots=True)
class _VolumeChangeCond(_ListenerCond[Listener]):
    percent: int
    MANAGER_FQN = "modules.volume_change.manager.get_volume_change_listener_manager"
