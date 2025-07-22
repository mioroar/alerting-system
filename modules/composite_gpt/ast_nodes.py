import time
import asyncpg
from dataclasses import dataclass, field, Field
from typing import Protocol, Set, Sequence


class EvalCtx(Protocol):
    """Контекст одного прохода CompositeListener — просто тонкая обёртка над db-pool."""
    db_pool: asyncpg.Pool



class Node:
    cooldown_sec: int = 0
    _last_ts: dict[str, float] = field(default_factory=dict, init=False)

    async def eval(self, ctx: EvalCtx) -> Set[str]:
        raise NotImplementedError

    def _apply_cd(self, tickers: Set[str]) -> Set[str]:
        if self.cooldown_sec == 0:
            return tickers

        # гарантируем, что _last_ts – именно dict
        last: dict[str, float] = getattr(self, "_last_ts", None)
        if last is None or isinstance(last, Field):
            last = {}
            setattr(self, "_last_ts", last)
        now = time.time()
        passed = {t for t in tickers if now - last.get(t, 0) >= self.cooldown_sec}
        for t in passed:
            last[t] = now
        return passed

    def intervals(self) -> Sequence[int]:
        return []


@dataclass
class AndNode(Node):
    left: Node
    right: Node

    async def eval(self, ctx: EvalCtx) -> Set[str]:
        a, b = await self.left.eval(ctx), await self.right.eval(ctx)
        return self._apply_cd(a & b)

    def intervals(self) -> Sequence[int]:
        return (*self.left.intervals(), *self.right.intervals())


@dataclass
class OrNode(Node):
    left: Node
    right: Node

    async def eval(self, ctx: EvalCtx) -> Set[str]:
        a, b = await self.left.eval(ctx), await self.right.eval(ctx)
        return self._apply_cd(a | b)

    def intervals(self) -> Sequence[int]:
        return (*self.left.intervals(), *self.right.intervals())


@dataclass
class _PriceCond(Node):
    percent: float
    interval: int
    direction: str = ">"
    _cache: set[str] = field(default_factory=set, init=False)

    async def eval(self, ctx: EvalCtx) -> Set[str]:
        if self._cache:
            return self._cache
        async with ctx.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (p.symbol)
                           p.symbol, p.price, p.ts
                    FROM price p
                    ORDER BY p.symbol, p.ts DESC
                ),
                past AS (
                    SELECT DISTINCT ON (pr.symbol)
                           pr.symbol, pr.price
                    FROM price pr
                    JOIN latest l USING (symbol)
                    WHERE pr.ts <= l.ts - $1 * INTERVAL '1 second'
                    ORDER BY pr.symbol, pr.ts DESC
                )
                SELECT l.symbol,
                       (l.price - past.price)*100/past.price AS chg
                FROM latest l
                JOIN past  USING (symbol);
                """,
                self.interval,
            )
        ok: set[str] = set()
        for r in rows:
            if self.direction == ">" and abs(r["chg"]) >= self.percent:
                ok.add(r["symbol"])
            elif self.direction == "<" and abs(r["chg"]) <= self.percent:
                ok.add(r["symbol"])
        self._cache = self._apply_cd(ok)
        return self._cache

    def intervals(self) -> Sequence[int]:
        return [self.interval]


@dataclass
class _VolumeCond(Node):
    amount: float
    interval: int
    direction: str = ">"
    _cache: set[str] = field(default_factory=set, init=False)

    async def eval(self, ctx: EvalCtx) -> Set[str]:
        if self._cache:
            return self._cache
        async with ctx.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH latest AS (
                    SELECT symbol, MAX(ts) AS max_ts
                    FROM volume
                    GROUP BY symbol
                ), cur AS (
                    SELECT v.symbol,
                           SUM(v.volume)::numeric AS cur_vol
                    FROM volume v
                    JOIN latest l USING (symbol)
                    WHERE v.ts > l.max_ts - $1 * INTERVAL '1 second'
                    GROUP BY v.symbol
                )
                SELECT symbol, cur_vol
                FROM cur;
                """,
                self.interval,
            )
        ok: set[str] = {
            r["symbol"]
            for r in rows
            if (r["cur_vol"] >= self.amount if self.direction == ">" else r["cur_vol"] <= self.amount)
        }
        self._cache = self._apply_cd(ok)
        return self._cache

    def intervals(self) -> Sequence[int]:
        return [self.interval]


@dataclass
class _VolChangeCond(Node):
    percent: float
    interval: int
    direction: str = ">"
    _cache: set[str] = field(default_factory=set, init=False)

    async def eval(self, ctx: EvalCtx) -> Set[str]:
        if self._cache:
            return self._cache
        async with ctx.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH latest AS (
                    SELECT symbol, MAX(ts) AS max_ts
                    FROM volume
                    GROUP BY symbol
                ),
                cur AS (
                    SELECT v.symbol,
                           SUM(v.volume)::numeric AS cur_vol
                    FROM volume v
                    JOIN latest l USING (symbol)
                    WHERE v.ts > l.max_ts - $1 * INTERVAL '1 second'
                    GROUP BY v.symbol
                ),
                prev AS (
                    SELECT v.symbol,
                           SUM(v.volume)::numeric AS prev_vol
                    FROM volume v
                    JOIN latest l USING (symbol)
                    WHERE v.ts > l.max_ts - 2*$1 * INTERVAL '1 second'
                      AND v.ts <= l.max_ts - $1 * INTERVAL '1 second'
                    GROUP BY v.symbol
                )
                SELECT c.symbol,
                       100*(c.cur_vol - p.prev_vol)/NULLIF(p.prev_vol,0) AS chg
                FROM cur c
                JOIN prev p USING (symbol)
                WHERE p.prev_vol <> 0;
                """,
                self.interval,
            )
        ok: set[str] = {
            r["symbol"]
            for r in rows
            if (r["chg"] >= self.percent if self.direction == ">" else r["chg"] <= -self.percent)
        }
        self._cache = self._apply_cd(ok)
        return self._cache

    def intervals(self) -> Sequence[int]:
        return [self.interval]
