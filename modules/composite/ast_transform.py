
from dataclasses import dataclass
from typing import Final, List, Sequence, Union
from lark import Token, Transformer, v_args


@dataclass(frozen=True, slots=True)
class Condition:
    """Элементарное условие: <module> <op> <params…>.

    Args:
        module (str): Имя модуля (price, volume, …).
        op (str): Строковый оператор сравнения ('>', '<=', …).
        params (List[float]): Список числовых параметров (порог, окно и т.д.).
    """
    module: str
    op: str
    params: List[float]


@dataclass(frozen=True, slots=True)
class And:
    """Конъюнкция A & B & …

    Args:
        items (List[Expr]): Список подвыражений.
    """
    items: List["Expr"]


@dataclass(frozen=True, slots=True)
class Or:
    """Дизъюнкция A | B | …

    Args:
        items (List[Expr]): Список подвыражений.
    """
    items: List["Expr"]


@dataclass(frozen=True, slots=True)
class Cooldown:
    """Постфикс expr@seconds (допустим только на корне).

    Args:
        expr (Expr): Выражение, к которому применяется cooldown.
        seconds (int): Количество секунд задержки.
    """
    expr: "Expr"
    seconds: int


Expr = Union[Condition, And, Or, Cooldown]


#: Допустимое количество числовых аргументов для каждого модуля.
#: Строка → кортеж вариантов (1,) — ровно одно число; (1, 2) — одно ИЛИ два; (2, 3) — два или три.
_PARAM_SPEC: Final[dict[str, tuple[int, ...]]] = {
    "oi":            (1,),
    "oi_sum":        (1,),
    "funding":       (2,),
    "price":         (2, 3),
    "volume":        (2, 3),
    "volume_change": (2, 3),
    "order":         (3,),
#    "spread":        (2,),
}


class AlertTransformer(Transformer):
    """Преобразует дерево Lark в AST, валидируя арность модулей.
    """

    def INT(self, tok: Token) -> int:
        """Преобразует токен в целое число.

        Args:
            tok (Token): Токен с целым числом.

        Returns:
            int: Целое число.
        """
        return int(tok)

    def NUMBER(self, tok: Token) -> float:
        """Преобразует токен в число с плавающей точкой.

        Args:
            tok (Token): Токен с числом.

        Returns:
            float: Число с плавающей точкой.
        """
        return float(tok)
    
    @v_args(inline=True)
    def param_tail(self, *nums: float) -> list[float]:
        return list(nums)

    @v_args(inline=True)
    def condition(
        self,
        module_tok: Token,
        op_tok: Token,
        first: float,
        *rest,
    ) -> Condition:
        """Строит Condition и проверяет число параметров.

        Args:
            module_tok (Token): Токен с именем модуля.
            op_tok (Token): Токен с оператором сравнения.
            first (float): Первый числовой параметр.
            *rest (Sequence[float]): Остальные числовые параметры.

        Returns:
            Condition: Экземпляр Condition.

        Raises:
            ValueError: Если модуль неизвестен или количество параметров некорректно.
        """
        module = module_tok.value

        if rest and isinstance(rest[0], list):
            params = [ first, *rest[0] ]
        else:
            params = [ first ]

        allowed = _PARAM_SPEC.get(module)
        if allowed is None:
            raise ValueError(f"Неизвестный модуль «{module}»")

        if len(params) not in allowed:
            expect = " или ".join(map(str, allowed))
            raise ValueError(
                f"Модуль «{module}» ожидает {expect} чисел, "
                f"получено {len(params)}: {params}"
            )

        return Condition(module, op_tok.value, params)

    def and_(self, items: List[Expr]) -> Expr:
        """A & B & C … ➜ And или одиночное под‑выражение.

        Args:
            items (List[Expr]): Список выражений.

        Returns:
            Expr: And, если выражений больше одного, иначе одиночное выражение.
        """
        return items[0] if len(items) == 1 else And(items)

    def or_(self, items: List[Expr]) -> Expr:
        """A | B | C … ➜ Or или одиночное под‑выражение.

        Args:
            items (List[Expr]): Список выражений.

        Returns:
            Expr: Or, если выражений больше одного, иначе одиночное выражение.
        """
        return items[0] if len(items) == 1 else Or(items)

    @v_args(inline=True)
    def cooldown(self, expr: Expr, seconds: int) -> Cooldown:
        """expr@seconds ➜ Cooldown.

        Args:
            expr (Expr): Выражение.
            seconds (int): Количество секунд задержки.

        Returns:
            Cooldown: Экземпляр Cooldown.
        """
        return Cooldown(expr, seconds)