"""开盘前与开盘后的信号计算（纯函数，不联网）。规则见 spec 第 3、4 节。"""
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from bnf.calendar import prev_trading_day, trading_days_between
from bnf.core import bias, buy_line, price_at_bias, s24, vol250
from bnf.holdings import Holding

EXIT_FRAC, HOLD_DAYS, AMBUSH_BAND, LOT = 0.4, 5, 1.05, 100
SWITCH_ON, SWITCH_CRASH = -0.05, -0.10
SPLIT_SUSPECT = 0.35     # 25 天内单日涨跌超过这个幅度（超出东证涨跌停范围），视为拆股没调整
MIN_FRESH = 0.5          # 开盘后检查：今天有价格的股票不足这个比例就警告


@dataclass
class Row:
    code: str
    name: str
    prev_close: float
    bias: float
    T: float
    trigger: float
    lot_cost: float
    vol: float
    vol_ratio: float | None = None   # 昨天成交量 / 之前 20 天均量；回测里 1.5~3 倍的反弹最好


@dataclass
class Advice:
    code: str
    name: str
    shares: int
    buy_price: float
    day: int
    target: float | None
    action: str          # LIMIT_SELL / SELL_AT_OPEN / SELL_BEFORE_0803 / WATCH / NO_DATA
    dist: float | None   # 目标价相对昨收


@dataclass
class Premarket:
    asof: date
    nk_close: float
    nk_bias: float
    switch: str          # OFF / ON / CRASH
    broken: list[Row]
    ambush: list[Row]
    holdings: list[Advice]
    warnings: list[str]
    broken_count: int = 0
    universe_n: int = 0
    rows: dict[str, Row] = field(default_factory=dict)


@dataclass
class PostOpen:
    crashed: list[tuple[Row, float]]
    hit: list[tuple[Advice, float]]
    warnings: list[str] = field(default_factory=list)


def _before(df: pd.DataFrame, today: date) -> pd.DataFrame:
    return df[df.index.date < today]


def _switch(nk_bias: float) -> str:
    if nk_bias <= SWITCH_CRASH:
        return "CRASH"
    return "ON" if nk_bias <= SWITCH_ON else "OFF"


def _vol_ratio(df: pd.DataFrame) -> float | None:
    if "Volume" not in df:
        return None
    v = df["Volume"]
    base = v.iloc[-21:-1].mean()
    return float(v.iloc[-1] / base) if base and base > 0 else None


def _row(code: str, df: pd.DataFrame, name: str) -> Row | None:
    close = df["Close"]
    b = bias(close)
    T = buy_line(b)
    if T is None:
        return None
    pc = float(close.iloc[-1])
    return Row(code, name, pc, float(b.iloc[-1]), T, price_at_bias(T, s24(close)), pc * LOT, vol250(close),
               _vol_ratio(df))


def _advice(h: Holding, df: pd.DataFrame | None, today: date, cfg: dict, name: str) -> Advice:
    day = trading_days_between(h.buy_date, today)
    no = Advice(h.code, name, h.shares, h.price, day, None, "NO_DATA", None)
    if df is None or df.empty:
        return no
    close = df["Close"]
    b = bias(close)
    T = buy_line(b[b.index.date < h.buy_date])
    if T is None:
        return no
    target = price_at_bias(EXIT_FRAC * T, s24(close))
    held = [i for i, d in enumerate(close.index.date) if d >= h.buy_date]
    hit = any(close.iloc[i] >= price_at_bias(EXIT_FRAC * T, close.iloc[i - 24:i].sum()) for i in held if i >= 24)
    odd = h.shares < LOT
    # day-1 = 已过的收盘数（按日历算），防止缺 K 线时漏掉第 6 天止损
    if hit or len(held) >= HOLD_DAYS or day - 1 >= HOLD_DAYS:
        action = "SELL_BEFORE_0803" if odd else "SELL_AT_OPEN"
    elif cfg.get("limit_sell") and not odd:
        action = "LIMIT_SELL"
    else:
        action = "WATCH"
    return Advice(h.code, name, h.shares, h.price, day, target, action, target / float(close.iloc[-1]) - 1)


def premarket(daily: dict[str, pd.DataFrame], holdings: list[Holding], today: date, cfg: dict,
              names: dict[str, str], universe: list[str]) -> Premarket:
    expected = prev_trading_day(today)
    d = {k: _before(v, today) for k, v in daily.items()}
    warnings, stale = [], []
    for k in list(universe) + [h.code for h in holdings] + ["^N225"]:
        df = d.get(k)
        if df is None or df.empty:
            if k in universe or k == "^N225":
                stale.append(k)
        elif df.index[-1].date() < expected:
            stale.append(k)
    if stale:
        warnings.append(f"{len(stale)} 只数据不是 {expected} 的最新收盘（已从买入列表排除）：{' '.join(sorted(set(stale))[:10])}")

    nk = d["^N225"]["Close"]
    nk_bias = float(bias(nk).iloc[-1])
    sw = _switch(nk_bias)
    held = {h.code for h in holdings}
    rows, suspect = {}, []
    for code in universe:
        df = d.get(code)
        if df is None or df.empty or code in stale:      # 过期的股票不给价格，免得按错的触发价挂单
            continue
        if df["Close"].pct_change().iloc[-25:].abs().max() > SPLIT_SUSPECT:
            suspect.append(code)
            continue
        r = _row(code, df, names.get(code, code))
        if r:
            rows[code] = r
    if suspect:
        warnings.append(f"疑似拆股未调整，已排除：{' '.join(suspect)}")
    by_vol = sorted(rows.values(), key=lambda r: -r.vol)
    # 已破线按破线当天的放量倍数从高到低排（用户从上往下买）；没有成交量数据的排最后
    broken_all = sorted((r for r in by_vol if r.bias <= r.T), key=lambda r: -(r.vol_ratio or 0))
    broken = [r for r in broken_all if r.code not in held]
    ambush = []
    if sw != "OFF" and cfg.get("ambush"):
        ambush = [r for r in by_vol if r.bias > r.T and r.code not in held and r.prev_close <= r.trigger * AMBUSH_BAND]
    advice = [_advice(h, d.get(h.code), today, cfg, names.get(h.code, h.code)) for h in holdings]
    return Premarket(today, float(nk.iloc[-1]), nk_bias, sw, broken, ambush, advice, warnings,
                     len(broken_all), len(rows), rows)


def postopen(pre: Premarket, latest: dict[str, dict], cfg: dict) -> PostOpen | None:
    def fresh(code):
        q = latest.get(code)
        return q if q and q.get("date") == pre.asof else None

    crashed, hit, checked = [], [], []
    if pre.switch != "OFF" and cfg.get("ambush"):
        skip = {r.code for r in pre.broken} | {a.code for a in pre.holdings}
        for r in sorted(pre.rows.values(), key=lambda r: -r.vol):
            if r.code in skip or r.bias <= r.T:
                continue
            q = fresh(r.code)
            checked.append(q)
            if q and q["last"] <= r.trigger:
                crashed.append((r, q["last"]))
    if cfg.get("limit_sell"):
        for a in pre.holdings:
            if a.action != "LIMIT_SELL":
                continue
            q = fresh(a.code)
            checked.append(q)
            if q and q["high"] >= a.target:
                hit.append((a, q["high"]))
    warnings = []
    n_fresh = sum(q is not None for q in checked)
    if checked and n_fresh < MIN_FRESH * len(checked):
        warnings.append(f"开盘数据还没更新（{n_fresh}/{len(checked)} 只有今天的价格），本次检查不可靠，请自己看一眼")
    return PostOpen(crashed, hit, warnings) if crashed or hit or warnings else None
