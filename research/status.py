import warnings, pickle, sys; warnings.filterwarnings("ignore")
import yfinance as yf, pandas as pd, numpy as np
names = pickle.load(open("bnf/px.pkl","rb"))["names"]
hist = pickle.load(open("bnf/px.pkl","rb"))["px"]
TIER = {"适合": "7267 8801 8001 6902 4519 7974 4063 4502 7741 8058 9433 6861 6273 9432 3382".split(),
        "一般": "6857 6981 9984 5401 6098".split()}
def price_at(T, s24): return (1+T)*s24/(24-T)   # 今天价格到多少时乖离率正好=T
tk = [f"{c}.T" for v in TIER.values() for c in v] + ["^N225"]
live = yf.download(tk, period="3mo", auto_adjust=False, progress=False, group_by="ticker")
nk = live["^N225"]["Close"].dropna()
s24 = nk.iloc[-25:-1].sum(); nkb = nk.iloc[-1]/((s24+nk.iloc[-1])/25)-1
print(f"日经 {nk.index[-1].date()} 现价 {nk.iloc[-1]:.0f}  今日乖离 {nkb:+.1%}  （-5%线={price_at(-0.05,s24):.0f}  -10%线={price_at(-0.10,s24):.0f}）\n")
rows=[]
for tier, codes in TIER.items():
    for c in codes:
        t=f"{c}.T"; cl = live[t]["Close"].dropna()   # 用未复权收盘，和券商App价格一致
        b = hist[t]["Close"]; bias=b/b.rolling(25).mean()-1; T=bias.quantile(0.02)
        s = cl.iloc[-25:-1].sum(); p = cl.iloc[-1]; nb = p/((s+p)/25)-1
        buy = price_at(T, s); sell = price_at(T*0.4, s)
        rows.append(dict(档=tier, 代码=c, 名称=names[c], 现价=p, 今日乖离=nb, 买入线=T, 今日触发价=buy, 距触发=buy/p-1, 卖出目标价=sell))
df=pd.DataFrame(rows).sort_values(["档","距触发"], ascending=[False,False])
pd.set_option("display.width",200)
print(df.to_string(index=False, formatters={"现价":"{:.0f}".format,"今日触发价":"{:.0f}".format,"卖出目标价":"{:.0f}".format,
      "今日乖离":"{:+.1%}".format,"买入线":"{:+.1%}".format,"距触发":"{:+.1%}".format}))
print("\n数据时间:", nk.index[-1])
