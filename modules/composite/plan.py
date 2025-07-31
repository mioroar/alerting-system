from functools import reduce
from operator import and_, or_
from typing import Callable, Mapping, Set

from .ast_transform import (
    And,
    Condition,
    Expr,
    Or,
)

TickerSet = Set[str]
Context   = Mapping[str, TickerSet]
PlanFn    = Callable[[Context], TickerSet]


def compile_plan(expr: Expr) -> PlanFn:
    """Преобразует AST в функцию объединения множеств.

    Args:
        expr: Корневой узел AST (And, Or, Condition).

    Returns:
        План‑функция: f(context) -> set(tickers).

    Raises:
        TypeError: Передан неподдерживаемый тип узла.
    """
    if isinstance(expr, Condition):
        module = expr.module

        def _leaf(ctx: Context, /) -> TickerSet:
            return ctx.get(module, set())
        return _leaf

    if isinstance(expr, And):
        subplans = [compile_plan(item) for item in expr.items]

        def _all(ctx: Context) -> TickerSet:
            return reduce(and_, (p(ctx) for p in subplans))
        return _all

    if isinstance(expr, Or):
        subplans = [compile_plan(item) for item in expr.items]

        def _any(ctx: Context) -> TickerSet:
            return reduce(or_, (p(ctx) for p in subplans))
        return _any

    raise TypeError(f"Unsupported node: {expr!r}")
