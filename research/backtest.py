import warnings, pickle, sys
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

d = pickle.load(open(sys.argv[1], "rb"))
px, names = d["px"], d["names"]
COST = 0.001  # 往返滑点+费用 0.1%

spx = px["^GSPC"]["Close"].pct_change()

def prep(df):
    df = df.copy()
    df["ma"] = df["Close"].rolling(25).mean()
    df["bias"] = df["Close"] / df["ma"] - 1
    # 东京 d 日之前最近一个美股交易日的涨跌
    df["us"] = spx.reindex(df.index - pd.Timedelta(days=1), method="ffill").values
    df["gap"] = df["Open"] / df["Close"].shift(1) - 1
    # 截至前一日的历史分位（无未来函数）
    for q in (0.01, 0.02, 0.05):
        df[f"q{int(q*100)}"] = df["bias"].shift(1).expanding(500).quantile(q)
    return df.dropna(subset=["bias"])

def run(df, thr, hold=2, exit_frac=0.4, us_filter=False, next_open=False):
    """thr: 标量或 Series（每日阈值）。收盘乖离率<=thr 收盘买，乖离率回到 thr*exit_frac 或持满 hold 天收盘卖。"""
    c, b = df["Close"].values, df["bias"].values
    o = df["Open"].values
    t = thr.values if isinstance(thr, pd.Series) else np.full(len(df), thr)
    us, gap = df["us"].values, df["gap"].values
    trades, i, n = [], 0, len(df)
    while i < n - 1:
        ok = not np.isnan(t[i]) and b[i] <= t[i]
        if ok and us_filter:
            ok = us[i] < -0.01 and gap[i] < 0
        if not ok:
            i += 1; continue
        if next_open:
            entry, start = o[i + 1], i + 1
        else:
            entry, start = c[i], i
        j = start + 1
        while j < n - 1 and j - start < hold and b[j] < t[i] * exit_frac:
            j += 1
        j = min(j, n - 1)
        trades.append((df.index[i], c[j] / entry - 1 - COST, j - start))
        i = j + 1
    return pd.DataFrame(trades, columns=["date", "ret", "days"])

def stats(tr):
    if len(tr) == 0:
        return dict(n=0)
    r = tr["ret"]
    g, l = r[r > 0].sum(), -r[r < 0].sum()
    return dict(n=len(r), win=(r > 0).mean(), avg=r.mean(), med=r.median(),
                worst=r.min(), pf=g / l if l > 0 else np.inf)

P = {t: prep(df) for t, df in px.items() if t.endswith(".T")}

def pooled(fn):
    trs = []
    for t, df in P.items():
        tr = fn(df); tr["tk"] = t; trs.append(tr)
    return pd.concat(trs, ignore_index=True)

fmt = lambda s: f"n={s['n']:5d} 胜率={s['win']:.0%} 均值={s['avg']:+.2%} 中位={s['med']:+.2%} 最差={s['worst']:+.1%} 盈亏比PF={s['pf']:.2f}" if s["n"] else "n=0"

print("=== 0. 基准：随便哪天收盘买、持有2天（50只合计）===")
base = pd.concat([(df["Close"].shift(-2) / df["Close"] - 1 - COST).dropna() for df in P.values()])
print(f"n={len(base)} 胜率={(base>0).mean():.0%} 均值={base.mean():+.2%}")

print("\n=== 1. 乖离率分桶后的未来收益（无交易规则，纯统计，不扣费）===")
rows = []
for df in P.values():
    f = pd.DataFrame({"b": df["bias"],
                      "r1": df["Close"].shift(-1) / df["Close"] - 1,
                      "r2": df["Close"].shift(-2) / df["Close"] - 1,
                      "r5": df["Close"].shift(-5) / df["Close"] - 1}).dropna()
    rows.append(f)
f = pd.concat(rows)
bins = [-1, -0.25, -0.20, -0.15, -0.12, -0.10, -0.08, -0.05, 0, 1]
f["bk"] = pd.cut(f["b"], bins)
g = f.groupby("bk", observed=True).agg(n=("b", "size"), r1=("r1", "mean"), r2=("r2", "mean"),
                                        r5=("r5", "mean"), win2=("r2", lambda x: (x > 0).mean()))
print(g.to_string(float_format=lambda x: f"{x:+.2%}" if abs(x) < 1 else f"{x:.0f}"))

print("\n=== 2. 固定阈值（所有股票同一条线），收盘买，回到阈值40%或满2天卖 ===")
for T in (-0.08, -0.10, -0.12, -0.15, -0.20):
    print(f"T={T:.0%}  ", fmt(stats(pooled(lambda df: run(df, T)))))

print("\n=== 3. 个股自适应阈值（用该股截至前一天的历史乖离率分位），满2天卖 ===")
for q in ("q1", "q2", "q5"):
    print(f"{q:3s} 单纯触发     ", fmt(stats(pooled(lambda df: run(df, df[q])))))
    print(f"{q:3s} +BNF扳机     ", fmt(stats(pooled(lambda df: run(df, df[q], us_filter=True)))))
    print(f"{q:3s} 次日开盘买   ", fmt(stats(pooled(lambda df: run(df, df[q], next_open=True)))))

print("\n=== 4. 持有天数敏感性（q2 单纯触发）===")
for h in (1, 2, 3, 5, 10):
    print(f"hold={h:2d} ", fmt(stats(pooled(lambda df: run(df, df["q2"], hold=h)))))

print("\n=== 5. 按年份（q2 单纯触发，hold=2）===")
tr = pooled(lambda df: run(df, df["q2"]))
tr["y"] = tr["date"].dt.year
for y, gg in tr.groupby("y"):
    s = stats(gg); print(y, fmt(s))

print("\n=== 6. 个股明细（q2 单纯触发，hold=2；q2/q5=全历史分位，现在=最新乖离率）===")
rows = []
for t, df in P.items():
    s = stats(run(df, df["q2"]))
    full = df["bias"]
    rows.append(dict(code=t[:-2], name=names[t[:-2]], n=s.get("n", 0), win=s.get("win"), avg=s.get("avg"),
                     pf=s.get("pf"), worst=s.get("worst"),
                     q1=full.quantile(0.01), q2=full.quantile(0.02), q5=full.quantile(0.05), now=full.iloc[-1]))
t6 = pd.DataFrame(rows).sort_values("avg", ascending=False)
pd.set_option("display.width", 200)
print(t6.to_string(index=False, formatters={k: (lambda x: f"{x:+.1%}") for k in ("avg", "worst", "q1", "q2", "q5", "now")}
                   | {"win": lambda x: f"{x:.0%}", "pf": lambda x: f"{x:.2f}"}))
t6.to_csv(sys.argv[2], index=False)
