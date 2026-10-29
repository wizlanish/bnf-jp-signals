import warnings, pickle, sys; warnings.filterwarnings("ignore")
import yfinance as yf
sec = {}
for line in open("bnf/n225.txt"):
    s, codes = line.strip().split("|")
    for c in codes.split(): sec[c] = s
tk = [f"{c}.T" for c in sec] + ["^N225"]
data = yf.download(tk, start="2010-01-01", auto_adjust=True, progress=False, group_by="ticker", threads=True)
px = {}
for t in tk:
    try:
        df = data[t].dropna(subset=["Close"])
        if len(df) > 600: px[t] = df
    except KeyError: pass
print("got", len(px), "missing/short", [t for t in tk if t not in px], file=sys.stderr)
pickle.dump({"px": px, "sec": sec}, open("bnf/px225.pkl", "wb"))
