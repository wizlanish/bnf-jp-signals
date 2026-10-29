"""持仓文件 holdings.json：[{"code","shares","price","buy_date"}]。文件由 routine 运行时写入，不进仓库。"""
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Holding:
    code: str
    shares: int
    price: float
    buy_date: date


def load_holdings(path="holdings.json") -> list[Holding]:
    p = Path(path)
    if not p.exists():
        return []
    return [Holding(str(h["code"]), int(h["shares"]), float(h["price"]), date.fromisoformat(h["buy_date"]))
            for h in json.loads(p.read_text() or "[]")]


def save_holdings(hs: list[Holding], path) -> None:
    Path(path).write_text(json.dumps(
        [{"code": h.code, "shares": h.shares, "price": h.price, "buy_date": h.buy_date.isoformat()} for h in hs],
        ensure_ascii=False, indent=2))
