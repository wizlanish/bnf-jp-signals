import numpy as np
import pandas as pd

from bnf.core import bias, buy_line, price_at_bias, s24, vol250


def test_price_at_bias_inverts_bias():
    p = price_at_bias(-0.10, 2400.0)
    assert abs(p - 0.9 * 2400 / 24.1) < 1e-9
    assert abs(p / ((2400 + p) / 25) - 1 - (-0.10)) < 1e-12


def test_bias_flat_is_zero():
    assert bias(pd.Series([100.0] * 30)).iloc[-1] == 0


def test_buy_line_needs_500_days():
    s = pd.Series(np.linspace(-.2, .2, 499), index=pd.bdate_range("2015-01-01", periods=499))
    assert buy_line(s) is None


def test_buy_line_is_2pct_quantile():
    s = pd.Series(np.linspace(-.2, .2, 1001), index=pd.bdate_range("2012-01-02", periods=1001))
    assert abs(buy_line(s) - s.quantile(0.02)) < 1e-12


def test_buy_line_ignores_pre_2010():
    idx = pd.bdate_range("2008-01-01", periods=1500)
    s = pd.Series(np.where(idx < "2010-01-01", -0.9, 0.0), index=idx)
    assert buy_line(s) == 0.0


def test_price_uses_split_adjusted_close():
    # 拆股后序列已统一到新股本：24 个 50 → 触发价落在 50 附近
    assert 40 < price_at_bias(-0.10, s24(pd.Series([50.0] * 30))) < 50


def test_vol250_constant_growth_is_zero():
    assert vol250(pd.Series(100 * 1.001 ** np.arange(300))) < 1e-9
