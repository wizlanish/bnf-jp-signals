"""python -m bnf {premarket|postopen} [--today YYYY-MM-DD] [--holdings PATH]

非交易日、或开盘后无事可报时不输出；出错时只输出一行 "⚠️ bnf 运行失败：..."，退出码 1。
"""
import argparse
import json
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from bnf import data
from bnf.calendar import is_trading_day
from bnf.holdings import load_holdings
from bnf.render import postopen_text, premarket_text
from bnf.signals import postopen, premarket


def _run(mode: str, today: date, holdings_path: str) -> str:
    if not is_trading_day(today):
        return ""
    cfg = json.loads((data.ROOT / "config.json").read_text())
    holdings = load_holdings(holdings_path)
    universe = data.universe()
    codes = sorted(set(universe) | {h.code for h in holdings})
    daily = data.load_daily(codes + ["^N225"])
    names = data.load_names(codes, persist=universe)
    pre = premarket(daily, holdings, today, cfg, names, universe)
    if mode == "premarket":
        return premarket_text(pre)
    po = postopen(pre, data.load_latest(codes), cfg)
    return postopen_text(po) if po else ""


def main() -> int:
    ap = argparse.ArgumentParser(prog="bnf")
    ap.add_argument("mode", choices=["premarket", "postopen"])
    ap.add_argument("--today", type=date.fromisoformat, default=datetime.now(ZoneInfo("Asia/Tokyo")).date())
    ap.add_argument("--holdings", default="holdings.json")
    args = ap.parse_args()
    try:
        out = _run(args.mode, args.today, args.holdings)
    except Exception as e:  # noqa: BLE001 — 推送里只报一行
        print(f"⚠️ bnf 运行失败：{type(e).__name__}: {e}")
        return 1
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
