from datetime import date

from bnf.calendar import is_trading_day, trading_days_between
from bnf.holdings import Holding, load_holdings, save_holdings


def test_trading_day_calendar():
    assert is_trading_day(date(2026, 10, 29))
    assert not is_trading_day(date(2026, 11, 3))   # 文化の日
    assert not is_trading_day(date(2026, 12, 31))
    assert not is_trading_day(date(2027, 1, 1))
    assert not is_trading_day(date(2027, 1, 2))
    assert not is_trading_day(date(2027, 1, 3))
    assert is_trading_day(date(2027, 1, 4))         # 大发会
    assert not is_trading_day(date(2026, 11, 1))   # 周日


def test_trading_days_between_skips_holiday():
    assert trading_days_between(date(2026, 11, 2), date(2026, 11, 4)) == 2  # 11/3 是假日
    assert trading_days_between(date(2026, 10, 29), date(2026, 10, 29)) == 1


def test_holdings_roundtrip(tmp_path):
    p = tmp_path / "h.json"
    save_holdings([Holding("6273", 3, 61014.0, date(2026, 11, 4))], p)
    assert load_holdings(p) == [Holding("6273", 3, 61014.0, date(2026, 11, 4))]
    assert load_holdings(tmp_path / "missing.json") == []


def test_prev_trading_day_skips_weekend_and_holiday():
    from bnf.calendar import prev_trading_day
    assert prev_trading_day(date(2026, 11, 4)) == date(2026, 11, 2)   # 跳过 11/3
    assert prev_trading_day(date(2026, 11, 2)) == date(2026, 10, 30)  # 跳过周末
