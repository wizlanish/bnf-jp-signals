from datetime import date

import numpy as np
import pandas as pd

from bnf.core import bias, buy_line, price_at_bias, s24
from bnf.holdings import Holding
from bnf.signals import postopen, premarket

TODAY = date(2026, 10, 29)
CFG = {"ambush": True, "limit_sell": True}


def frame(closes, end="2026-10-28"):
    idx = pd.bdate_range(end=end, periods=len(closes))
    c = pd.Series(np.asarray(closes, dtype=float), index=idx)
    return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c})


def walk(n=700, seed=0):
    rng = np.random.default_rng(seed)
    return 1000 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))


def nk_with_bias(target):
    return frame([100.0] * 699 + [price_at_bias(target, 2400.0)])


def with_last(closes, factor):
    c = np.array(closes, dtype=float)
    c[-1] = c[-2] * factor
    return c


def run(daily, holdings=(), cfg=CFG, universe=None):
    universe = universe if universe is not None else [k for k in daily if k != "^N225"]
    return premarket(daily, list(holdings), TODAY, cfg, {}, universe)


def test_switch_thresholds():
    s = {"1111": frame(walk())}
    assert run({**s, "^N225": nk_with_bias(-0.0501)}).switch == "ON"
    assert run({**s, "^N225": nk_with_bias(-0.0499)}).switch == "OFF"
    assert run({**s, "^N225": nk_with_bias(-0.1001)}).switch == "CRASH"


def test_broken_when_prev_close_below_line():
    c = with_last(walk(), 0.80)
    p = run({"1111": frame(c), "^N225": nk_with_bias(-0.06)})
    assert [r.code for r in p.broken] == ["1111"]
    r = p.broken[0]
    cs = pd.Series(c)
    assert abs(r.T - buy_line(bias(frame(c)["Close"]))) < 1e-12
    assert abs(r.trigger - price_at_bias(r.T, s24(cs))) < 1e-9
    assert p.broken_count == 1


def test_ambush_only_when_switch_on_and_within_5pct():
    base = walk(seed=1)
    df = frame(base)
    T = buy_line(bias(df["Close"]))
    trig = price_at_bias(T, s24(df["Close"].iloc[:-1]))   # 用前 24 天算出“昨天”的触发价水平作参照
    near, far = base.copy(), base.copy()
    # 让昨收落在 今日触发价*1.04 / *1.06：迭代求解（昨收本身影响 S24）
    def set_last(arr, mult):
        for _ in range(50):
            t = price_at_bias(T, arr[-24:].sum())
            arr[-1] = t * mult
        return arr
    near, far = set_last(near, 1.04), set_last(far, 1.06)
    on = run({"1111": frame(near), "2222": frame(far), "^N225": nk_with_bias(-0.06)})
    assert [r.code for r in on.ambush] == ["1111"]
    off = run({"1111": frame(near), "^N225": nk_with_bias(-0.01)})
    assert off.ambush == []
    assert run({"1111": frame(near), "^N225": nk_with_bias(-0.06)}, cfg={"ambush": False, "limit_sell": True}).ambush == []


def test_held_stock_excluded_from_lists():
    c = with_last(walk(), 0.80)
    p = run({"1111": frame(c), "^N225": nk_with_bias(-0.06)}, holdings=[Holding("1111", 100, 900.0, date(2026, 10, 27))])
    assert p.broken == [] and p.broken_count == 1


def test_short_history_skipped():
    p = run({"1111": frame(with_last(walk(499), 0.5)), "^N225": nk_with_bias(-0.06)})
    assert p.broken == [] and p.ambush == []


def _held(closes, shares, buy_date, cfg=CFG):
    df = frame(closes)
    p = run({"1111": df, "^N225": nk_with_bias(-0.01)}, holdings=[Holding("1111", shares, 900.0, buy_date)], cfg=cfg)
    return p.holdings[0]


def test_holding_target_hit_odd_lot():
    c = walk(seed=2)
    T = buy_line(bias(frame(c[:-2])["Close"]))
    c[-1] = price_at_bias(0.4 * T, c[-25:-1].sum()) * 1.01          # 昨收站上目标价
    a = _held(c, 3, date(2026, 10, 27))
    assert a.action == "SELL_BEFORE_0803"


def test_holding_time_stop():
    c = walk(seed=3)
    c[-8:] = c[-9] * 0.85                                           # 一直没反弹
    a = _held(c, 100, date(2026, 10, 21))                           # 10/21 起已过 5 个收盘
    assert a.day == 7 and a.action == "SELL_AT_OPEN"


def test_holding_limit_sell_vs_watch():
    c = walk(seed=3)
    c[-3:] = c[-4] * 0.85
    assert _held(c, 100, date(2026, 10, 27)).action == "LIMIT_SELL"
    assert _held(c, 100, date(2026, 10, 27), cfg={"ambush": True, "limit_sell": False}).action == "WATCH"
    assert _held(c, 3, date(2026, 10, 27)).action == "WATCH"


def test_holding_outside_universe():
    daily = {"1111": frame(walk()), "1306": frame(walk(seed=5)), "^N225": nk_with_bias(-0.01)}
    p = premarket(daily, [Holding("1306", 10, 2500.0, date(2026, 10, 27)), Holding("9999", 100, 1.0, date(2026, 10, 27))],
                  TODAY, CFG, {}, ["1111"])
    acts = {a.code: a.action for a in p.holdings}
    assert acts["1306"] in {"LIMIT_SELL", "WATCH", "SELL_AT_OPEN"} and acts["9999"] == "NO_DATA"


def test_stale_data_warns():
    p = run({"1111": frame(walk(), end="2026-10-27"), "^N225": nk_with_bias(-0.01)})
    assert p.warnings


def test_rows_use_only_data_before_today():
    c = walk()
    df = frame(np.append(c, c[-1] * 0.5), end="2026-10-29")       # 今天这根 K 线不该被用到
    assert run({"1111": df, "^N225": nk_with_bias(-0.01)}).rows["1111"].prev_close == c[-1]


def test_postopen_crash_and_hit():
    c = walk(seed=1)
    pre = run({"1111": frame(c), "^N225": nk_with_bias(-0.06)})
    trig = pre.rows["1111"].trigger
    po = postopen(pre, {"1111": {"open": trig, "high": trig, "low": trig * 0.99, "last": trig * 0.99, "date": TODAY}}, CFG)
    assert [r.code for r, _ in po.crashed] == ["1111"]
    assert postopen(pre, {"1111": {"open": trig * 2, "high": trig * 2, "low": trig * 2, "last": trig * 2, "date": TODAY}}, CFG) is None
    c2 = walk(seed=3); c2[-3:] = c2[-4] * 0.85
    pre2 = run({"1111": frame(c2), "^N225": nk_with_bias(-0.01)}, holdings=[Holding("1111", 100, 900.0, date(2026, 10, 27))])
    tgt = pre2.holdings[0].target
    po2 = postopen(pre2, {"1111": {"open": tgt, "high": tgt * 1.01, "low": tgt, "last": tgt, "date": TODAY}}, CFG)
    assert [a.code for a, _ in po2.hit] == ["1111"]


def test_stale_stock_excluded_from_lists():
    c = with_last(walk(), 0.80)
    p = run({"1111": frame(c, end="2026-10-27"), "2222": frame(walk(seed=7)), "^N225": nk_with_bias(-0.06)})
    assert "1111" not in p.rows and p.broken == []
    assert any("1111" in w for w in p.warnings)


def test_split_suspect_excluded():
    c = walk()
    c[-10:] = c[-10:] * 0.5                                         # 拆股没调整：单日 -50%
    p = run({"1111": frame(c), "^N225": nk_with_bias(-0.06)})
    assert "1111" not in p.rows
    assert any("拆股" in w and "1111" in w for w in p.warnings)


def test_time_stop_survives_missing_bars():
    c = walk(seed=3)
    c[-8:] = c[-9] * 0.85
    df = frame(c).drop(pd.bdate_range(end="2026-10-28", periods=8)[2:4])  # 少了两根 K 线
    p = run({"1111": df, "^N225": nk_with_bias(-0.01)}, holdings=[Holding("1111", 100, 900.0, date(2026, 10, 21))])
    assert p.holdings[0].day == 7 and p.holdings[0].action == "SELL_AT_OPEN"


def test_postopen_warns_when_open_data_missing():
    c = walk(seed=1)
    pre = run({"1111": frame(c), "2222": frame(walk(seed=8)), "^N225": nk_with_bias(-0.06)})
    stale = {k: {"open": 1, "high": 1, "low": 1, "last": 1, "date": date(2026, 10, 28)} for k in ("1111", "2222")}
    po = postopen(pre, stale, CFG)
    assert po is not None and po.warnings and not po.crashed


def test_postopen_quiet_when_nothing_to_check():
    pre = run({"1111": frame(walk(seed=1)), "^N225": nk_with_bias(-0.01)})
    assert postopen(pre, {}, CFG) is None
