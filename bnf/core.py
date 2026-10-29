"""乖离率相关的纯计算。所有价格序列都是 yfinance auto_adjust=False 的 Close（已拆股调整、未分红调整）。"""
import numpy as np
import pandas as pd


def bias(close: pd.Series) -> pd.Series:
    """收盘价相对 25 日简单均线的乖离率。"""
    return close / close.rolling(25).mean() - 1


def buy_line(bias_hist: pd.Series, start="2010-01-01", q=0.02, min_obs=500) -> float | None:
    """个股买入线：start 之后乖离率的 q 分位数。bias_hist 须由调用方截断到昨天。"""
    h = bias_hist[bias_hist.index >= pd.Timestamp(start)].dropna()
    if len(h) < min_obs:
        return None
    return float(h.quantile(q))


def price_at_bias(target_bias: float, s24: float) -> float:
    """今天收盘价为多少时，乖离率恰好等于 target_bias。由 P = (1+T)(S24+P)/25 解出。"""
    return (1 + target_bias) * s24 / (24 - target_bias)


def s24(close: pd.Series) -> float:
    """最近 24 个收盘价之和。"""
    return float(close.iloc[-24:].sum())


def vol250(close: pd.Series) -> float:
    """最近 250 个日收益率的年化波动率。"""
    return float(close.pct_change().iloc[-250:].std() * np.sqrt(250))
