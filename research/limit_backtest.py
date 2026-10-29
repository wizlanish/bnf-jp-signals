"""spec 第 7 节：限价卖（A）和埋伏限价买（B）分开回测，结果写入 config.json。

运行：python research/limit_backtest.py   （在仓库根目录）
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bnf.core import bias, price_at_bias  # noqa: E402

warnings.filterwarnings("ignore")
COST, HOLD, EXIT_FRAC, SWITCH, AMBUSH_BAND, MARGIN = 0.001, 5, 0.4, -0.05, 1.05, 0.005


def n225_codes():
    out = []
    for line in (ROOT / "n225.txt").read_text().splitlines():
        if "|" in line:
            out += line.split("|", 1)[1].split()
    return out


def load():
    tk = [f"{c}.T" for c in n225_codes()] + ["^N225"]
    raw = yf.download(tk, start="2010-01-01", auto_adjust=False, progress=False, group_by="ticker", threads=True)
    return {t: raw[t][["Open", "High", "Low", "Close"]].dropna() for t in tk if t in raw.columns.get_level_values(0)}


def prep(df, nk_switch):
    c = df["Close"]
    b = bias(c)
    T = b.shift(1).expanding(500).quantile(0.02)          # 截至昨天
    s = c.rolling(24).sum().shift(1)                       # 截至昨天的 S24
    out = pd.DataFrame({"o": df["Open"], "h": df["High"], "l": df["Low"], "c": c, "b": b, "T": T, "s24": s,
                        "on": nk_switch.reindex(df.index, method="ffill").fillna(False)})
    out["trig"] = price_at_bias(out["T"], out["s24"])
    return out


def hold_and_exit(d, i, entry, T, method, same_day_limit=True):
    """第 i 天按 entry 买入，T 在买入时固定。返回 (收益, 卖出日索引)。
    same_day_limit=False：盘中限价买入的那天不允许限价卖——不知道最高价在最低价之前还是之后。"""
    n = len(d)
    o, h, c, s = d["o"].values, d["h"].values, d["c"].values, d["s24"].values
    for k in range(HOLD):
        j = i + k
        if j >= n - 1:
            return None
        tgt = price_at_bias(EXIT_FRAC * T, s[j])
        if method == "limit" and h[j] >= tgt and (k > 0 or same_day_limit):
            return max(tgt, o[j]) / entry - 1 - COST, j
        if method == "close" and c[j] >= tgt:
            return o[j + 1] / entry - 1 - COST, j + 1
    j = i + HOLD
    if j >= n:
        return None
    return o[j] / entry - 1 - COST, j


def run(data, nk_switch):
    rows = {"A_close": [], "A_limit": [], "B_close": [], "B_limit": []}
    for t, df in data.items():
        if t == "^N225" or len(df) < 600:
            continue
        d = prep(df, nk_switch)
        o, l, c, b, T, trig, on = (d[k].values for k in ("o", "l", "c", "b", "T", "trig", "on"))
        for kind in ("A", "B"):
            for method in ("close", "limit"):
                i, n = 1, len(d)
                while i < n - 1:
                    if np.isnan(T[i]) or not on[i]:
                        i += 1; continue
                    broken = b[i - 1] <= T[i]
                    if kind == "A" and broken:
                        entry = o[i]
                    elif kind == "B" and not broken and c[i - 1] <= trig[i] * AMBUSH_BAND and l[i] <= trig[i]:
                        entry = min(trig[i], o[i])
                    else:
                        i += 1; continue
                    r = hold_and_exit(d, i, entry, T[i], method, same_day_limit=(kind == "A"))
                    if r is None:
                        break
                    rows[f"{kind}_{method}"].append(r[0])
                    i = r[1] + 1
    return {k: np.array(v) for k, v in rows.items()}


def stats(r):
    g, l = r[r > 0].sum(), -r[r < 0].sum()
    return dict(n=len(r), win=float((r > 0).mean()), avg=float(r.mean()), pf=float(g / l) if l else float("inf"),
                worst=float(r.min()))


def main():
    data = load()
    nk = data["^N225"]["Close"]
    nk_switch = (bias(nk) <= SWITCH).shift(1)              # 昨收日经乖离
    R = run(data, nk_switch)
    S = {k: stats(v) for k, v in R.items()}
    for k, s in S.items():
        print(f"{k:8s} n={s['n']:5d} 胜率={s['win']:.0%} 均值={s['avg']:+.2%} PF={s['pf']:.2f} 最差={s['worst']:+.1%}")
    limit_sell = S["A_limit"]["avg"] >= S["A_close"]["avg"] - MARGIN
    a_method = "limit" if limit_sell else "close"
    ambush = S[f"B_{a_method}"]["avg"] >= S[f"A_{a_method}"]["avg"] - MARGIN
    notes = (f"A 开盘卖 {S['A_close']['avg']:+.2%} vs 限价卖 {S['A_limit']['avg']:+.2%}；"
             f"B 埋伏({a_method}) {S[f'B_{a_method}']['avg']:+.2%} vs 对照 {S[f'A_{a_method}']['avg']:+.2%}")
    (ROOT / "config.json").write_text(json.dumps({"ambush": bool(ambush), "limit_sell": bool(limit_sell), "notes": notes},
                                                 ensure_ascii=False, indent=2) + "\n")
    print("config:", {"ambush": ambush, "limit_sell": limit_sell}, notes)


if __name__ == "__main__":
    main()
