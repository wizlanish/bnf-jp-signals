import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
T = pd.read_pickle("bnf/trades225.pkl"); P = T[T.nkb <= -0.05].dropna(subset=["vol", "mom"]).copy()
P["combo"] = P.groupby("date")["vol"].rank(pct=True) + P.groupby("date")["mom"].rank(pct=True, ascending=False)
def pick(df, key, asc, k=5):
    return df.sort_values(key, ascending=asc).groupby("date").head(k)
def s(x): r = x.ret; return f"n={len(r):4d} 胜率={(r>0).mean():.0%} 均值={r.mean():+.2%} 最差={r.min():+.1%}"
print("同一天信号数分布：中位", P.groupby("date").size().median(), " 最大", P.groupby("date").size().max())
for lab, key, asc in (("全部信号", None, None), ("每天取波动率最高5只", "vol", False), ("每天取一年涨幅最低5只", "mom", True),
                      ("每天取综合(高波动+弱势)前5", "combo", False), ("每天取波动率最低5只(反例)", "vol", True)):
    x = P if key is None else pick(P, key, asc)
    print(f"{lab:22s}", s(x), "| 后段2018+", s(x[x.date >= "2018"]))
