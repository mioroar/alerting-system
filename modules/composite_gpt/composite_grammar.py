from lark import Lark
from functools import lru_cache

_GRAMMAR = r"""
?start: expr

?expr: expr "|" and_expr   -> or
     | and_expr

?and_expr: and_expr "&" term   -> and
         | term

?term: atom
     | "(" expr ")" ["@" INT]  -> cooldown_term

?atom: price_cond
     | volume_cond
     | volchg_cond

price_cond: "price" OP NUMBER "%" INT ["@" INT]
volume_cond: "volume" OP NUMBER INT ["@" INT]
volchg_cond: "volume_change" OP NUMBER INT ["@" INT]

OP: ">" | "<"
NUMBER: /[0-9]+(\.[0-9]+)?/
INT: /[0-9]+/

%import common.WS
%ignore WS
"""

@lru_cache(maxsize=1)
def get_parser() -> Lark:
    return Lark(_GRAMMAR, start="start", parser="lalr", propagate_positions=True)
