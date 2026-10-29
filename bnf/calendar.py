"""东证交易日历：周一到周五，排除日本节假日和年末年始（12/31、1/1–1/3）。"""
from datetime import date, timedelta

import jpholiday


def is_trading_day(d: date) -> bool:
    if d.weekday() >= 5 or jpholiday.is_holiday(d):
        return False
    if (d.month, d.day) in {(12, 31), (1, 1), (1, 2), (1, 3)}:
        return False
    return True


def trading_days_between(start: date, end: date) -> int:
    """start 到 end 之间（两端都含）的交易日数。"""
    n, d = 0, start
    while d <= end:
        n += is_trading_day(d)
        d += timedelta(days=1)
    return n


def prev_trading_day(d: date) -> date:
    """d 之前（不含 d）最近的交易日。"""
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d
