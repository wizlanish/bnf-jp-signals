import re
import sys
from datetime import date

import pytest

from bnf import __main__ as cli
from bnf.render import postopen_text, premarket_text
from bnf.signals import Advice, PostOpen, Premarket, Row

D = date(2026, 10, 29)


def row(i, bias=-0.2, T=-0.15):
    return Row(f"{1000 + i}", f"N{i}", 1000.0, bias, T, 900.0, 100000.0, 0.3)


def pre(switch="OFF", broken=(), ambush=(), holdings=(), warnings=()):
    return Premarket(D, 64131.0, -0.031, switch, list(broken), list(ambush), list(holdings), list(warnings),
                     broken_count=len(broken), universe_n=223)


def test_quiet_day_one_liner():
    lines = premarket_text(pre()).splitlines()
    assert len(lines) == 2 and lines[1] == "今天不动"
    assert lines[0] == "日经 64,131｜乖离 -3.1%｜开关 关闭｜破线 0/223"


def test_list_truncated_at_15():
    out = premarket_text(pre("ON", broken=[row(i) for i in range(40)]))
    assert sum(1 for l in out.splitlines() if "开盘买" in l and l[:4].isdigit()) == 15
    assert "…共40只" in out


def test_history_reference_when_switch_on():
    out = premarket_text(pre("ON", broken=[row(i) for i in range(12)]))
    assert "胜率65%" in out and "+2.1%" in out


def test_off_day_lists_codes_only():
    out = premarket_text(pre("OFF", broken=[row(1), row(2)]))
    assert "个股破线 2 只（大盘未恐慌，历史上不赚钱）：1001 1002" in out
    assert "今天不动" in out


def test_holding_lines():
    a = Advice("6273", "SMC", 3, 61014.0, 2, 65941.0, "SELL_BEFORE_0803", 0.03)
    b = Advice("7267", "Honda", 100, 1560.0, 3, 1672.0, "LIMIT_SELL", 0.05)
    out = premarket_text(pre(holdings=[a, b]))
    assert "8:03前市价卖" in out and "限价卖 1,672" in out and "第2天" in out and "今天不动" not in out


def test_no_share_counts():
    out = premarket_text(pre("ON", broken=[row(1)], ambush=[row(2, bias=-0.1)]))
    assert not re.search(r"买入?\d+股|股数", out)


def test_warnings_last():
    out = premarket_text(pre(warnings=["3 只数据不是最新"]))
    assert out.splitlines()[-1] == "⚠️ 3 只数据不是最新"


def test_postopen_text():
    a = Advice("7267", "Honda", 100, 1560.0, 3, 1672.0, "LIMIT_SELL", 0.05)
    out = postopen_text(PostOpen([(row(1), 880.0)], [(a, 1680.0)]))
    assert "1001" in out and "880" in out and "1,680" in out


def test_cli_silent_on_holiday(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bnf", "premarket", "--today", "2026-11-03"])
    assert cli.main() == 0
    assert capsys.readouterr().out == ""


def test_cli_error_line(capsys, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("yahoo down")
    monkeypatch.setattr(cli.data, "load_daily", boom)
    monkeypatch.setattr(sys, "argv", ["bnf", "premarket", "--today", "2026-10-29"])
    assert cli.main() == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and out[0].startswith("⚠️ bnf 运行失败：RuntimeError: yahoo down")


def test_postopen_text_shows_warnings():
    out = postopen_text(PostOpen([], [], ["开盘数据还没更新（0/5 只有今天的价格）"]))
    assert out.splitlines()[-1].startswith("⚠️ 开盘数据还没更新")


def test_names_cache_only_persists_universe(tmp_path, monkeypatch):
    from bnf import data

    class T:
        def __init__(self, t): self.info = {"shortName": f"N-{t}"}
    monkeypatch.setattr(data.yf, "Ticker", T)
    cache = tmp_path / "names.json"
    names = data.load_names(["1111", "9999"], cache=cache, persist=["1111"])
    assert names == {"1111": "N-1111.T", "9999": "N-9999.T"}
    assert "9999" not in cache.read_text()


def test_broken_line_shows_volume_ratio():
    r = row(1)
    r.vol_ratio = 2.1
    assert "放量2.1倍" in premarket_text(pre("ON", broken=[r]))
    r.vol_ratio = 0.8
    assert "缩量0.8倍" in premarket_text(pre("ON", broken=[r]))
