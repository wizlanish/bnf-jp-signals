import warnings, sys; warnings.filterwarnings("ignore")
exec(open("bnf/backtest.py").read().split('fmt = lambda')[0])
fmt = lambda s: f"n={s['n']:5d} 胜率={s['win']:.0%} 均值={s['avg']:+.2%} 最差={s['worst']:+.1%} PF={s['pf']:.2f}" if s["n"] else "n=0"
nk = px["^N225"]["Close"]; nkb = (nk/nk.rolling(25).mean()-1)
for t, df in P.items():
    df["nkb_prev"] = nkb.reindex(df.index, method="ffill").shift(1)   # 昨收的日经乖离，开盘前已知
    s24 = df["Close"].rolling(24).sum().shift(1)
    df["obias"] = df["Open"] / ((s24 + df["Open"]) / 25) - 1          # 用今天开盘价代替收盘价算的乖离

def run_exec(df, mode, hold=5, exit_frac=0.4, mkt=None):
    """全部可执行：
    mode='prevclose': 昨收乖离<=阈值 -> 今天开盘买
    mode='open'     : 今天开盘价乖离<=阈值 -> 今天开盘买（9:00 看到开盘价马上下单，按开盘价近似）
    卖出：某天收盘乖离>=目标 -> 次日开盘卖；或持有满 hold 天后的次日开盘卖"""
    o, b = df["Open"].values, df["bias"].values
    thr = df["q2"].values  # q2 只用截至前一日的数据
    sig = df["bias"].shift(1).values if mode == "prevclose" else df["obias"].values
    nkp = df["nkb_prev"].values
    trades, i, n = [], 1, len(df)
    while i < n - 1:
        ok = not np.isnan(thr[i]) and sig[i] <= thr[i] and (mkt is None or nkp[i] <= mkt)
        if not ok: i += 1; continue
        entry = o[i]; j = i
        while j < n - 2 and j - i < hold - 1 and b[j] < thr[i] * exit_frac:
            j += 1
        x = j + 1  # 次日开盘卖
        trades.append((df.index[i], o[x] / entry - 1 - COST, x - i))
        i = x + 1
    return pd.DataFrame(trades, columns=["date", "ret", "days"])

for mkt, lab in ((None, "不看大盘"), (-0.05, "昨收日经乖离<=-5%"), (-0.10, "昨收日经乖离<=-10%")):
    print(f"\n=== {lab} ===")
    for mode, ml in (("prevclose", "昨收算→今天开盘买"), ("open", "开盘价算→开盘就买")):
        for h in (2, 5):
            print(f"{ml} 持有≤{h}天  ", fmt(stats(pooled(lambda df: run_exec(df, mode, hold=h, mkt=mkt)))))
