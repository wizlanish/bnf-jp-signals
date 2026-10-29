"""云端可行性冒烟测试：能否从 Yahoo 拉到日股历史数据。"""
import time
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent


def n225_codes():
    codes = []
    for line in (ROOT / "n225.txt").read_text().splitlines():
        if "|" in line:
            codes += line.split("|", 1)[1].split()
    return codes


def main():
    for t in ["7203.T", "9984.T", "^N225"]:
        df = yf.download(t, start="2010-01-01", auto_adjust=False, progress=False)
        last = df.index[-1].date() if len(df) else None
        print(f"{t}: rows={len(df)} last={last}")

    tickers = [f"{c}.T" for c in n225_codes()]
    t0 = time.time()
    data = yf.download(tickers, start="2010-01-01", auto_adjust=False, progress=False,
                       group_by="ticker", threads=True)
    ok = sum(1 for t in tickers if t in data.columns.get_level_values(0) and data[t]["Close"].notna().sum() > 0)
    print(f"bulk: ok={ok}/{len(tickers)} seconds={time.time() - t0:.0f}")


if __name__ == "__main__":
    main()
