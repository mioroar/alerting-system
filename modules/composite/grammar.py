from lark import Lark
from functools import lru_cache

GRAMMAR = r"""
?start: root_expr

?root_expr: expr
            | expr "@" INT         -> cooldown

?expr: or_
?or_: and_ ("|" and_)*           -> or_
?and_: factor ("&" factor)*      -> and_
?factor: condition
        | "(" expr ")"

condition: MODULE OP NUMBER param_tail?   -> condition
?param_tail: NUMBER+

MODULE: /[a-zA-Z_][a-zA-Z0-9_]*/
OP: ">" | "<" | ">=" | "<=" | "==" | "!="
NUMBER: SIGNED_NUMBER
INT: /[0-9]+/

%import common.SIGNED_NUMBER
%import common.WS_INLINE
%ignore WS_INLINE
"""


@lru_cache(maxsize=1)
def get_parser() -> Lark:
    """Возвращает настроенный Lark‑парсер"""
    return Lark(GRAMMAR, parser="lalr", propagate_positions=True)
