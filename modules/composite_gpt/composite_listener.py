import asyncpg
from typing import List

from bot.settings import bot

from .ast_nodes import Node, AndNode, OrNode  
from .composite_grammar import get_parser
from .ast_builder import build_ast

class _Ctx:
    __slots__ = ("db_pool",)
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool

class CompositeListener:
    """
    Listener, исполняющий булево выражение над ценой/объёмом/Δобъёмом.

    • один и тот же тикер должен удовлетворять всем leaf-условиям внутри AND  
    • частота проверок = минимальный interval среди всех leaf-узлов  
    • cooldown’ы на узлах уже учитываются самим AST  
    """
    def __init__(self, condition_id: str, expression: str, ast: Node) -> None:
        self.condition_id = condition_id
        self.expression = expression
        self._ast: Node = ast
        self.interval: int = min(ast.intervals())
        self.subscribers: List[int] = []

    def add_subscriber(self, uid: int) -> None:
        if uid not in self.subscribers:
            self.subscribers.append(uid)

    def remove_subscriber(self, uid: int) -> None:
        if uid in self.subscribers:
            self.subscribers.remove(uid)

    async def check_and_notify(self, db_pool: asyncpg.Pool) -> None:
        if not self.subscribers:
            return
        # обнуляем кеши leaf-узлов на этот проход
        def _clear_cache(node: Node):
            if hasattr(node, "_cache"):
                node._cache.clear()        # type: ignore
            if isinstance(node, (AndNode, OrNode)):
                _clear_cache(node.left)
                _clear_cache(node.right)

        _clear_cache(self._ast)

        ok_tickers = await self._ast.eval(_Ctx(db_pool))
        if not ok_tickers:
            return
        base = f"🟢 Условие «{self.expression}» выполнено для:"

        # сортировка + пачки по ~4000 симв (запас на заголовок)
        line, chunk = "", [base]
        for sym in sorted(ok_tickers):
            entry = f" {sym},"
            if len(line) + len(entry) > 3800:        # 3800 ≈ 4096-base
                chunk.append(line.rstrip(","))
                line = ""
            line += entry
        if line:
            chunk.append(line.rstrip(","))           # финальный хвост
        msg_list = ["\n".join(chunk[i : i + 2])      # base + список
                    for i in range(0, len(chunk), 2)]

        for uid in self.subscribers:
            for msg in msg_list:
                await bot.send_message(uid, msg)

    # ------------- фабричный метод -------------
    @classmethod
    def from_expression(cls, expr: str) -> "CompositeListener":
        parse_tree = get_parser().parse(expr)
        ast = build_ast(parse_tree)
        cid = str(hash(expr))
        return cls(cid, expr, ast)
