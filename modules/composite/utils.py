from typing import Generator

from .ast_transform import Condition, Expr, And, Cooldown, Or
from .grammar import get_parser
from .ast_transform import AlertTransformer


def collect_conditions(expr: Expr) -> Generator[Condition, None, None]:
    """Рекурсивно собирает все листовые Condition узлы.

    Args:
        expr: Произвольный узел AST.

    Yields:
        Condition: Каждый найденный лист.
    """
    if isinstance(expr, Condition):
        yield expr
        return
    for sub in getattr(expr, "items", ()):
        yield from collect_conditions(sub)


def parse_expression(text: str) -> Expr:
    """Парсит строку выражения в AST.

    Args:
        text: Строка, пришедшая от пользователя.

    Returns:
        Expr: Корневой узел AST.

    Raises:
        (Lark)UnexpectedInput / ValueError: При синтаксической или
            семантической ошибке.
    """
    tree = get_parser().parse(text)
    return AlertTransformer().transform(tree)

def ast_to_string(expr: Expr) -> str:
    """Преобразует AST в текст вида
       price > 3 300 | volume > 1_000_000 60 @120
    """
    if isinstance(expr, Condition):
        return f"{expr.module} {expr.op} " + " ".join(map(str, expr.params))

    if isinstance(expr, And):
        return " & ".join(ast_to_string(e) for e in expr.items)

    if isinstance(expr, Or):
        return " | ".join(ast_to_string(e) for e in expr.items)

    if isinstance(expr, Cooldown):
        return f"{ast_to_string(expr.expr)} @{expr.seconds}"

    raise TypeError(expr)     # на случай неизвестного типа