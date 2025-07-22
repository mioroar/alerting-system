from decimal import Decimal
from lark import Transformer, v_args, Tree       # <— добавили Tree для отладки
from typing import Any

from .ast_nodes import (
    AndNode, OrNode, _PriceCond, _VolumeCond, _VolChangeCond, Node
)


class _Builder(Transformer):
    def or_expr(self, items):
        return items[0]

    # ───── корневой узел ─────
    def start(self, items):
        """Правило start → expr. Просто пробрасываем вниз."""
        return items[0]

    # ───── pass-through для коротких вариантов ─────
    def expr(self, items):
        return items[0]

    def and_expr(self, items):
        return items[0]

    def term(self, items):
        return items[0]

    # ───── базовые типы ─────
    INT = v_args(inline=True)(int)
    NUMBER = v_args(inline=True)(lambda self, t: float(Decimal(t.value)))

    # ───── логические узлы ─────
    def or_(self, items):
        left, right = items
        return OrNode(left, right)

    def and_(self, items):
        left, right = items
        return AndNode(left, right)

    # ───── cooldown ─────
    def cooldown_term(self, items):
        """
        Разбирает конструкцию  ( expr ) [@INT]
        children может включать '(', ')', '@' + любые
        вложенные списки.  Нужно вытащить:
            • node  – узел-условие AST
            • cd    – целое (@cooldown, опц.)
        """
        node = None
        cd = 0

        # рекурсивный обход всех уровней вложенности
        def walk(obj: Any):
            nonlocal node, cd
            if isinstance(obj, list):
                for sub in obj:
                    walk(sub)
            elif isinstance(obj, int):
                cd = obj
            elif hasattr(obj, "intervals"):      # любой из наших AST-классов
                node = obj

        walk(items)

        if node is None:
            raise ValueError("Внутри (@…) нет пригодного условия")

        node.cooldown_sec = cd
        return node

    # ───── атомы ─────
    def price_cond(self, items):
        op, num, interval, *cd = items
        n = _PriceCond(percent=num, interval=interval, direction=op.value)
        if cd:
            n.cooldown_sec = cd[0]
        return n

    def volume_cond(self, items):
        op, amount, interval, *cd = items
        n = _VolumeCond(amount=amount, interval=interval, direction=op.value)
        if cd:
            n.cooldown_sec = cd[0]
        return n

    def volchg_cond(self, items):
        op, num, interval, *cd = items
        n = _VolChangeCond(percent=num, interval=interval, direction=op.value)
        if cd:
            n.cooldown_sec = cd[0]
        return n
    
    def __default__(self, data, children, meta):
        return children[0] if len(children) == 1 else children


def build_ast(parse_tree: "Tree") -> Node:
    node = _Builder().transform(parse_tree)

    # ← маленькая страховка: если что-то пошло не так, увидим раннюю ошибку
    if isinstance(node, Tree):
        raise RuntimeError("Transformer did not collapse parse tree to AST node")

    return node
