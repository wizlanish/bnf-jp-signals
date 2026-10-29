import warnings, pickle; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
d = pickle.load(open("bnf/px225.pkl", "rb")); px, sec = d["px"], d["sec"]
COST = 0.001
nk = px["^N225"]["Close"]; nkb = nk / nk.rolling(25).mean() - 1

def trades_for(t, df, hold=5, exit_frac=0.4):
    c, o = df["Close"], df["Open"]
    bias = c / c.rolling(25).mean() - 1
    thr = bias.shift(1).expanding(500).quantile(0.02)          # 截至前一日
    sig = bias.shift(1)                                         # 昨收乖离
    nkp = nkb.reindex(df.index, method="ffill").shift(1)
    r = c.pct_change()
    vol = (r.rolling(250).std() * np.sqrt(250)).shift(1)        # 截至昨天的年化波动
    mom = (c / c.shift(250) - 1).shift(1)                       # 截至昨天的一年涨幅
    b, ov, th, sg, nv = bias.values, o.values, thr.values, sig.values, nkp.values
    out, i, n = [], 1, len(df)
    while i < n - 1:
        if np.isnan(th[i]) or sg[i] > th[i]:
            i += 1; continue
        j = i
        while j < n - 2 and j - i < hold - 1 and b[j] < th[i] * exit_frac:
            j += 1
        x = j + 1
        out.append((t[:-2], sec[t[:-2]], df.index[i], ov[x] / ov[i] - 1 - COST, nv[i], vol.iloc[i], mom.iloc[i]))
        i = x + 1
    return out

rows = []
for t, df in px.items():
    if t == "^N225": continue
    rows += trades_for(t, df)
T = pd.DataFrame(rows, columns=["code", "sec", "date", "ret", "nkb", "vol", "mom"])
T.to_pickle("bnf/trades225.pkl")

def st(x):
    r = x["ret"]; g, l = r[r > 0].sum(), -r[r < 0].sum()
    return pd.Series(dict(n=len(r), win=(r > 0).mean(), avg=r.mean(), pf=g / l if l else np.nan))
f = lambda s: f"n={int(s.n):5d} 胜率={s.win:.0%} 均值={s.avg:+.2%} PF={s.pf:.2f}"
P = T[T.nkb <= -0.05]   # 大盘开关打开时
print("=== A. 225 只全体（可执行：昨收信号→开盘买→开盘卖，≤5天）===")
print("不看大盘     ", f(st(T)))
print("日经<=-5%   ", f(st(P)))
print("日经<=-10%  ", f(st(T[T.nkb <= -0.10])))

IS, OOS = T[T.date < "2018-01-01"], T[T.date >= "2018-01-01"]
print("\n=== B. 按个股过去成绩选股，样本外还灵吗？（2010-17 选，2018-26 检验；不看大盘以保证样本量）===")
s_is = IS.groupby("code").apply(st); s_is = s_is[s_is.n >= 8]
s_oos = OOS.groupby("code").apply(st)
j = s_is[["avg"]].join(s_oos[["avg", "n"]], rsuffix="_oos").dropna()
print(f"股票数 {len(j)}，样本内均值 与 样本外均值 的秩相关 = {j['avg'].rank().corr(j['avg_oos'].rank()):+.3f}")
j["tier"] = pd.qcut(j["avg"], 3, labels=["样本内差", "样本内中", "样本内好"])
for k, g in j.groupby("tier", observed=True):
    print(f"{k}：样本外 ", f(st(OOS[OOS.code.isin(g.index)])), "| 大盘开关下", f(st(OOS[OOS.code.isin(g.index) & (OOS.nkb <= -0.05)])))

print("\n=== C. 按行业：前后两段是否一致（大盘开关下）===")
a = P[P.date < "2018-01-01"].groupby("sec").apply(st); b = P[P.date >= "2018-01-01"].groupby("sec").apply(st)
s = a[["n", "avg"]].join(b[["n", "avg"]], lsuffix="_前", rsuffix="_后").join(P.groupby("sec").apply(st)[["n", "avg", "pf"]])
s = s[s.n >= 20].sort_values("avg", ascending=False)
print(f"行业前后段均值秩相关 = {s['avg_前'].rank().corr(s['avg_后'].rank()):+.3f}")
print(s.to_string(formatters={c: "{:+.2%}".format for c in ("avg_前", "avg_后", "avg")} | {"pf": "{:.2f}".format}))

print("\n=== D. 按事前可知的特征分组（大盘开关下），前后两段分别看 ===")
for col, lab in (("vol", "过去一年波动率"), ("mom", "过去一年涨幅")):
    P2 = P.dropna(subset=[col]).copy()
    P2["bk"] = P2.groupby(P2.date.dt.year)[col].transform(lambda x: pd.qcut(x.rank(method="first"), 3, labels=["低", "中", "高"]))
    print(f"-- {lab} 三分位（每年内分组）")
    for k, g in P2.groupby("bk", observed=True):
        print(f"  {k}  全期", f(st(g)), "| 前段", f(st(g[g.date < '2018'])), "| 后段", f(st(g[g.date >= '2018'])))
