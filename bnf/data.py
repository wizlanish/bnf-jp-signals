"""yfinance 薄封装。价格一律用 auto_adjust=False 的列（已拆股调整、未分红调整，与券商 App 一致）。"""
import json
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
COLS = ["Open", "High", "Low", "Close"]


def _ticker(code: str) -> str:
    return code if code.startswith("^") else f"{code}.T"


def universe() -> list[str]:
    out = []
    for line in (ROOT / "n225.txt").read_text().splitlines():
        if "|" in line:
            out += line.split("|", 1)[1].split()
    return out


def load_daily(codes: list[str], start="2010-01-01") -> dict[str, pd.DataFrame]:
    tk = [_ticker(c) for c in codes]
    raw = yf.download(tk, start=start, auto_adjust=False, progress=False, group_by="ticker", threads=True)
    have = set(raw.columns.get_level_values(0))
    return {c: raw[t][COLS].dropna() for c, t in zip(codes, tk) if t in have and raw[t]["Close"].notna().any()}


def load_latest(codes: list[str]) -> dict[str, dict]:
    tk = [_ticker(c) for c in codes]
    raw = yf.download(tk, period="5d", auto_adjust=False, progress=False, group_by="ticker", threads=True)
    out = {}
    for c, t in zip(codes, tk):
        if t not in set(raw.columns.get_level_values(0)):
            continue
        df = raw[t][COLS].dropna()
        if len(df):
            last = df.iloc[-1]
            out[c] = {"open": float(last["Open"]), "high": float(last["High"]), "low": float(last["Low"]),
                      "last": float(last["Close"]), "date": df.index[-1].date()}
    return out


def load_names(codes: list[str], cache=ROOT / "data" / "names.json", persist=None) -> dict[str, str]:
    """shortName，取不到就用代码本身。只有 persist 里的代码（成分股）写进缓存：
    data/names.json 是提交到公开仓库的，持仓代码不能进去。"""
    names = json.loads(cache.read_text()) if cache.exists() else {}
    keep = set(codes if persist is None else persist)
    missing = [c for c in codes if c not in names]
    for c in missing:
        try:
            names[c] = yf.Ticker(_ticker(c)).info.get("shortName") or c
        except Exception:
            names[c] = c
    if any(c in keep for c in missing):
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(json.dumps({k: v for k, v in names.items() if k in keep or k not in missing},
                                    ensure_ascii=False, indent=0))
    return {c: names.get(c, c) for c in codes}
