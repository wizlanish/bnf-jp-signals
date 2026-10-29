# 日股乖离率抄底信号推送 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 每个东证交易日 7:30 和 9:30（JST），由云端定时任务把日经 225 乖离率抄底信号和持仓卖出提示推送到用户手机。

**Architecture：**
- Python 包 `bnf/` 由纯计算（core、signals）、数据（data）、日历和持仓（calendar、holdings）、文本渲染（render）几部分组成，CLI `python -m bnf premarket|postopen` 把推送文本打印到 stdout。
- 云端 routine 用 `git clone` 拉取公开仓库，把指令里写好的持仓存成 holdings.json，运行 CLI，再用 PushNotification 发出。
- 持仓存放在仓库里的 `holdings.json`，由本地 Claude 按用户的口述更新。

**Tech Stack：** Python 3.11+、pandas、numpy、yfinance、jpholiday、pytest；Claude Code routines；GitHub 公开仓库（wizlanish，只放代码）。

**Spec：** `docs/superpowers/specs/2026-10-29-bnf-jp-signals-design.md`。所有执行者都先读它。

## Global Constraints

- 股票池：`n225.txt`，格式为每行一个行业，"行业|代码 代码 …"。
- 价格一律用 yfinance `auto_adjust=False` 的 `Close`、`Open`、`High`、`Low`。这几列已按拆股调整、没有按分红调整，和券商 App 显示的价格一致；**不用 `Adj Close`**。
- 乖离率：bias = Close / Close.rolling(25).mean() − 1。
- 个股买入线 T：截至昨天的乖离率历史从 2010-01-01 起取 2% 分位数，样本少于 500 天的返回 None，这只股票不出信号。
- 触发价：P = (1+T)·S24/(24−T)。卖出目标价：P = (1+0.4T)·S24/(24−0.4T)。S24 = 截至昨天的最近 24 个收盘价之和。
- 大盘开关：用日经 `^N225` 昨收的乖离率判断。≤ −0.05 为 ON，≤ −0.10 为 CRASH，其余为 OFF。
- 持仓：买入日算第 1 天，只数东证交易日。第 1~5 天里任何一天收盘价 ≥ 当天的目标价，下一个交易日卖；第 5 天收盘还没到目标，第 6 天开盘卖。
- 股数 < 100 的持仓视为 ひと株，只能下市价单：8:03 前下单按当天开盘价成交，8:03~14:30 下单按当天收盘价成交。
- 推送里不出现股数建议。
- 交易日：周一到周五，排除日本节假日（jpholiday）和 12/31、1/1~1/3。
- 计算不能用到推送时刻还不知道的数据。

## Review Focus

1. **最近 24 天内有拆股**：yfinance 的 Close 已按拆股调整，所以算出来的触发价应当在现在的价位上，不会差一个拆股倍数。由 Task 2 的 `test_price_uses_split_adjusted_close` 覆盖。
2. **数据过期或缺失**：yfinance 没返回昨天的 K 线，或者某只股票整体缺数据。推送应当写出警告，而不是安静地显示"今天不动"。由 Task 5 的 `test_stale_data_warns` 覆盖。
3. **持仓不在股票池里**（比如某只 ETF）：仍然用它自己的历史算目标价；历史不够 500 天的，提示"无法计算"。由 Task 5 的 `test_holding_outside_universe` 覆盖。
4. **新上市、历史不足 500 天的成分股**（如 285A）：直接跳过，不报错。由 Task 2 的 `test_buy_line_needs_500_days` 和 Task 5 的 `test_short_history_skipped` 覆盖。
5. **日本节假日或年末年始被定时任务触发**：完全不输出，因此也不推送。由 Task 3 的 `test_trading_day_calendar` 和 Task 6 的 `test_cli_silent_on_holiday` 覆盖。

---

## File Structure

```
bnf/__init__.py
bnf/__main__.py      CLI 入口：premarket / postopen
bnf/core.py          乖离率、买入线、反推价格、波动率（纯函数）
bnf/calendar.py      东证交易日、持仓天数
bnf/holdings.py      读写 holdings.json
bnf/data.py          yfinance 日线和盘中最新价
bnf/signals.py       大盘状态、破线、埋伏、持仓建议、开盘后检查（纯函数）
bnf/render.py        中文推送文本
config.json          {"ambush": bool, "limit_sell": bool}，由 Task 4 写入
holdings.json        持仓（gitignore，由 routine 运行时写入）
research/limit_backtest.py   spec 第 7 节的回测
tests/…
CLAUDE.md            本地会话里更新持仓的规则（通过 RemoteTrigger 改 routine 的指令）
requirements.txt
```

---

### Task 1: 仓库骨架 + 云端可行性验证（关卡）

**Files:**
- Create: `requirements.txt`、`bnf/__init__.py`、`.gitignore`
- Create: `scripts/cloud_smoke.py`

**Interfaces:**
- Produces: 公开仓库 `wizlanish/bnf-jp-signals`；一份结论，说明云端能不能用 yfinance，以及能不能git clone 公开仓库。

- [ ] **Step 1**：`requirements.txt` 写入 yfinance、pandas、numpy、jpholiday、pytest。`.gitignore` 写入 `__pycache__/`、`.venv/`、`data/cache/`。
- [ ] **Step 2**：`scripts/cloud_smoke.py` 要做的事：
  1. 下载 `["7203.T", "9984.T", "^N225"]` 从 2010-01-01 至今的日线，打印每只的行数和最后一天的日期；
  2. 用 n225.txt 全部代码做一次批量下载，打印成功只数和耗时。
- [ ] **Step 3**：本地运行 `python scripts/cloud_smoke.py`。预期：3 只都超过 3,000 行；全量 ≥ 220 只成功。
- [ ] **Step 4**：commit。**先问用户**是否同意建私有仓库，同意后运行 `gh repo create wizlanish/bnf-jp-signals --private --source . --push`。
- [ ] **Step 5**：用 schedule skill 建一个一次性的云端测试 routine，不绑定仓库。prompt 是：git clone https://github.com/wizlanish/bnf-jp-signals，切到 feat/signals 分支，安装 requirements，运行 `python scripts/cloud_smoke.py`，用 PushNotification 发出最后 5 行输出。等它跑完。
- [ ] **Step 6**：判定结果。
  - 推送里的成功只数 ≥ 220：通过，继续往下做。
  - Yahoo 被封、被限流，或者拉不到仓库：**停下来**，把现象告诉用户。按 spec 第 6 节的备选方案（换数据源，或改用 GitHub Actions 预先计算）改计划后再继续。
- [ ] **Step 7**：删除测试 routine。

### Task 2: 核心计算 `bnf/core.py`

**Interfaces:**
- Produces:
  - `bias(close: pd.Series) -> pd.Series`
  - `buy_line(bias_hist: pd.Series, start="2010-01-01", q=0.02, min_obs=500) -> float | None`：传进来的 bias_hist 只能包含截至昨天的数据，由调用方负责截断。
  - `price_at_bias(target_bias: float, s24: float) -> float`
  - `s24(close: pd.Series) -> float`：最后 24 个值之和。
  - `vol250(close: pd.Series) -> float`：最近 250 个日收益率的标准差 × √250。

- [ ] **Step 1：写失败的测试** `tests/test_core.py`
```python
def test_price_at_bias_inverts_bias():
    p = price_at_bias(-0.10, 2400.0)
    assert abs(p - 0.9 * 2400 / 24.1) < 1e-9
    assert abs(p / ((2400 + p) / 25) - 1 - (-0.10)) < 1e-12

def test_bias_flat_is_zero():
    assert bias(pd.Series([100.0] * 30)).iloc[-1] == 0

def test_buy_line_needs_500_days():
    assert buy_line(pd.Series(np.linspace(-.2, .2, 499), index=pd.bdate_range("2015-01-01", periods=499))) is None

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
```
- [ ] **Step 2**：运行 `pytest tests/test_core.py -v`，预期全部 FAIL（import error）。
- [ ] **Step 3**：实现上面 5 个函数。
- [ ] **Step 4**：运行 `pytest tests/test_core.py -v`，预期全部 PASS。
- [ ] **Step 5**：commit `feat: core bias math`。

### Task 3: 日历与持仓 `bnf/calendar.py`、`bnf/holdings.py`

**Interfaces:**
- Produces:
  - `is_trading_day(d: date) -> bool`
  - `trading_days_between(start: date, end: date) -> int`：两端都算，只数交易日。
  - `@dataclass Holding(code: str, shares: int, price: float, buy_date: date)`
  - `load_holdings(path="holdings.json") -> list[Holding]`
  - `save_holdings(hs, path)`
  - `holdings.json` 的格式：`[{"code": "6273", "shares": 3, "price": 61014, "buy_date": "2026-11-04"}]`。文件不存在或内容为 `[]`，都视为没有持仓。

- [ ] **Step 1：写失败的测试** `tests/test_calendar_holdings.py`
```python
def test_trading_day_calendar():
    assert is_trading_day(date(2026, 10, 29))
    assert not is_trading_day(date(2026, 11, 3))   # 文化の日
    assert not is_trading_day(date(2026, 12, 31))
    assert is_trading_day(date(2027, 1, 4))         # 1/4 是大发会，要算交易日
    assert not is_trading_day(date(2026, 11, 1))   # 周日

def test_trading_days_between_skips_holiday():
    assert trading_days_between(date(2026, 11, 2), date(2026, 11, 4)) == 2  # 11/3 是假日

def test_holdings_roundtrip(tmp_path):
    p = tmp_path / "h.json"
    save_holdings([Holding("6273", 3, 61014.0, date(2026, 11, 4))], p)
    assert load_holdings(p) == [Holding("6273", 3, 61014.0, date(2026, 11, 4))]
    assert load_holdings(tmp_path / "missing.json") == []
```
- [ ] **Step 2**：运行 `pytest tests/test_calendar_holdings.py -v`，预期 FAIL。
- [ ] **Step 3**：实现。节假日用 `jpholiday.is_holiday`，再加上 12/31、1/1、1/2、1/3。
- [ ] **Step 4**：运行 `pytest tests/test_calendar_holdings.py -v`，预期 PASS。
- [ ] **Step 5**：commit `feat: TSE calendar and holdings store`。

### Task 4: 限价买卖回测 → `config.json`（spec 第 7 节）

**Files:** Create `research/limit_backtest.py`、`config.json`

**Interfaces:**
- Consumes: `bnf.core.bias`、`buy_line`、`price_at_bias`、`s24`
- Produces: `config.json`，格式为 `{"ambush": bool, "limit_sell": bool, "notes": str}`

- [ ] **Step 1：写回测**，要求如下。
  - 数据：日经 225（n225.txt）从 2010 年起的日线，用 Global Constraints 规定的价格列。
  - 条件：只取日经昨收乖离率 ≤ −0.05 的日子，往返成本 0.1%，最多持有 5 天，第 6 天开盘止损。
  - 每天的 T 只用截至前一天的数据。
  - **A（限价卖）**：交易集合是"昨收 bias ≤ T，今天开盘买"。分别用两种卖法回测，对比结果：
    1. 现有卖法："收盘 ≥ 当天目标价 → 下一个开盘卖"；
    2. 限价卖："当天 High ≥ 当天目标价就成交，成交价 = max(目标价, Open)"。
  - **B（埋伏买）**：交易集合是"昨收不满足 bias ≤ T，但昨收 ≤ 今天触发价 × 1.05"的股票。当天 Low ≤ 触发价就成交，成交价 = min(触发价, Open)。卖法采用 A 的判定结果。对照组是同一时期"昨收破线、开盘买"的交易。
  - 每组都输出：笔数、胜率、平均每笔、PF、最差一笔。
- [ ] **Step 2**：运行 `python research/limit_backtest.py`，预期打印 A、B 两组的对比表。
- [ ] **Step 3：判定并写入 config.json**。每个功能单独判定：平均每笔比对照组低不到 0.5 个百分点，设为 true，否则 false。`notes` 里写上两组的平均每笔数字。
- [ ] **Step 4**：把对比表贴给用户看，不用等批准。commit `research: limit-order backtest and config`。

### Task 5: 信号计算 `bnf/data.py`、`bnf/signals.py`

**Interfaces:**
- Consumes: Task 2、3 的全部函数；`config.json`
- Produces:
  - `data.load_daily(codes: list[str], start="2010-01-01") -> dict[str, pd.DataFrame]`：key 是 "7203" 或 "^N225"，列为 Open、High、Low、Close，DatetimeIndex。
  - `data.load_latest(codes) -> dict[str, dict]`：值是 `{"open", "high", "low", "last", "date"}`，取今天盘中的最新一根日线。
  - `data.load_names(codes) -> dict[str, str]`：取 shortName，缓存到 `data/names.json`，取不到就返回代码本身。
  - `@dataclass Row(code, name, prev_close, bias, T, trigger, lot_cost, vol)`
  - `@dataclass Advice(code, name, shares, buy_price, day, target, action)`。action 只能是以下 4 个值之一："LIMIT_SELL"、"SELL_AT_OPEN"、"SELL_BEFORE_0803"、"WATCH"；算不出目标价时为 "NO_DATA"。
  - `@dataclass Premarket(asof: date, nk_close, nk_bias, switch: str, broken: list[Row], ambush: list[Row], holdings: list[Advice], warnings: list[str])`
  - `signals.premarket(daily, holdings, today: date, cfg: dict, names) -> Premarket`
  - `@dataclass PostOpen(crashed: list[tuple[Row, float]], hit: list[tuple[Advice, float]])`
  - `signals.postopen(pre: Premarket, latest, cfg) -> PostOpen | None`：两个列表都为空时返回 None。

规则：
- broken 和 ambush 都按 vol 从高到低排序，并排除已持有的股票。
- ambush 只在 switch 不是 OFF、而且 `cfg["ambush"]` 为 true 时才计算，条件是昨收 ≤ trigger × 1.05。
- 持仓的 action 判定（T 用买入日前一天能算出的值）：
  1. 买入以来任何一个收盘价 ≥ 当天目标价，或者昨天已经是第 5 天以后：股数 < 100 返回 SELL_BEFORE_0803，否则返回 SELL_AT_OPEN。
  2. 否则，`cfg["limit_sell"]` 为 true 且股数 ≥ 100：返回 LIMIT_SELL。
  3. 其余返回 WATCH。
- 任何一只股票最后一根 K 线的日期不是"今天之前最近的那个交易日"，就往 warnings 里加一条。
- postopen：
  - crashed 只在 switch 不是 OFF、而且 `cfg["ambush"]` 为 true 时计算：最新价 ≤ 今天触发价，并且不在 broken 名单里。
  - hit 只在 `cfg["limit_sell"]` 为 true 时计算：持仓今天的最高价 ≥ 目标价。

- [ ] **Step 1：写失败的测试** `tests/test_signals.py`。用合成的 600 天 DataFrame，不联网。
```python
def test_switch_thresholds(): # 构造日经昨收乖离 -0.05 / -0.0499 / -0.10 → "ON" / "OFF" / "CRASH"
def test_broken_when_prev_close_below_line(): # 最后一天暴跌到 bias < T → 出现在 broken，trigger == price_at_bias(T, s24)
def test_ambush_only_when_switch_on_and_within_5pct(): # switch OFF → ambush == []；ON 时昨收 = trigger*1.04 入选，trigger*1.06 不入选
def test_held_stock_excluded_from_lists():
def test_short_history_skipped(): # 499 天的股票不在任何列表里，也不抛异常
def test_holding_target_hit_odd_lot(): # shares=3，昨收 ≥ 目标价 → "SELL_BEFORE_0803"
def test_holding_time_stop(): # 已经第 6 天、没到过目标价，shares=100 → "SELL_AT_OPEN"
def test_holding_limit_sell_vs_watch(): # cfg limit_sell=True、shares=100 → "LIMIT_SELL"；False → "WATCH"
def test_holding_outside_universe(): # 代码不在 n225 里但有数据 → 照常给出目标价；没有数据 → action == "NO_DATA"
def test_stale_data_warns(): # 最后一根 K 线比前一交易日早 → warnings 非空
def test_postopen_crash_and_hit(): # latest.last ≤ trigger 且不在 broken → crashed；持仓 high ≥ target → hit；都没有 → None
```
每个测试的断言写在注释里，具体实现照注释来。
- [ ] **Step 2**：运行 `pytest tests/test_signals.py -v`，预期 FAIL。
- [ ] **Step 3**：实现 `signals.py`。`data.py` 是 yfinance 的薄封装，`group_by="ticker"`、`threads=True`；历史数据可以缓存到 `data/cache/`，由实现者决定。
- [ ] **Step 4**：运行 `pytest -v`，预期全部 PASS。再用真实数据跑一次 `python -c "from bnf import data,signals; …"` 冒烟测试，看打印出的 Premarket 是否合理：今天的 switch 应该是 OFF，日经乖离率在 -3% 左右。
- [ ] **Step 5**：commit `feat: signal computation`。

### Task 6: 渲染与 CLI `bnf/render.py`、`bnf/__main__.py`

**Interfaces:**
- Consumes: Task 5 的 `Premarket`、`PostOpen`
- Produces:
  - `render.premarket_text(p: Premarket) -> str`
  - `render.postopen_text(po: PostOpen) -> str`
  - CLI `python -m bnf {premarket|postopen} [--today YYYY-MM-DD]`：非交易日不输出任何内容；postopen 返回 None 时也不输出；出异常时只输出一行 `⚠️ bnf 运行失败：<异常类型>: <消息>`，退出码为 1。

文案（照 spec 4.1、4.2）：
- 第一行：`日经 64,131｜乖离 -3.1%｜开关 关闭｜破线 2/223`
- 开关打开时，第二行写历史参考。档位和数字照抄：

  | 破线数 | 胜率 | 平均每笔 |
  |---|---|---|
  | 1~3 | 43% | -0.9% |
  | 4~10 | 57% | +1.4% |
  | 11~30 | 65% | +2.1% |
  | 31+ | 71% | +2.9% |

- broken 每行：`9984 SBG 昨收4,669 乖离-14.6%/线-14.4% 一手46.7万 → 开盘买（ひと株须8:03前）`
- 开关关闭时，broken 只写一行：`个股破线 N 只（大盘未恐慌，历史上不赚钱）：9984 6981…`
- ambush 每行：`9433 KDDI 限价 2,677（一手股适用）`
- 持仓每行按 action 写：
  - LIMIT_SELL：`限价卖 X`
  - SELL_AT_OPEN：`开盘市价卖`
  - SELL_BEFORE_0803：`8:03前市价卖`
  - WATCH：`观望 目标X`
  - NO_DATA：`无法计算`

  每行都附上 `第n天` 和 `距目标±x%`。
- 什么都没有时：`今天不动`
- 每个列表最多 15 行，超出的写 `…共N只`。
- 价格加千分位，取整。
- warnings 放在最后，每条前面加 `⚠️`。

- [ ] **Step 1：写失败的测试** `tests/test_render_cli.py`
```python
def test_quiet_day_one_liner(): # switch OFF、没有破线、没有持仓 → 正好 2 行，第 2 行是 "今天不动"
def test_list_truncated_at_15(): # 40 只 broken → 只有 15 行明细，外加 "…共40只"
def test_no_share_counts(): # 输出里不出现 "股数" 或 "买入\d+股" 这类文字
def test_cli_silent_on_holiday(capsys): # --today 2026-11-03 → stdout 为空，退出码 0
def test_cli_error_line(monkeypatch, capsys): # 让 data.load_daily 抛异常 → 只有一行，以 "⚠️ bnf 运行失败" 开头，退出码 1
```
- [ ] **Step 2**：运行 `pytest tests/test_render_cli.py -v`，预期 FAIL。
- [ ] **Step 3**：实现 render 和 CLI。
- [ ] **Step 4**：运行 `pytest -v`，预期全部 PASS。再跑 `python -m bnf premarket`，用真实数据打印今天的推送文本给用户看。
- [ ] **Step 5**：commit `feat: push text and CLI`，然后 push。

### Task 7: 持仓更新规则 + 正式 routine 上线

**Files:** Create `CLAUDE.md`

- [ ] **Step 1**：写 `CLAUDE.md`，内容是本地会话的规则：
  - 用户说"买了 <代码/名称> <股数> <价格>"：往 holdings.json 加一条，buy_date 取今天（JST）。
  - 用户说"卖了 …"：删除对应的那条。
  - 两种情况都用 RemoteTrigger update 改两个 routine 指令里的持仓 JSON（routine ID 记在记忆里），然后复述一遍更新后的持仓。
  - 持仓绝不提交进仓库，因为仓库是公开的。
- [ ] **Step 2**：在用户的全局记忆 `bnf-japan-strategy.md` 里补一行："用户在任何目录说买了或卖了日股，都去 ~/bnf-jp-signals 按 CLAUDE.md 更新持仓。"
- [ ] **Step 3**：用 schedule skill 建两个 routine，都不绑定仓库，在指令里 git clone 公开仓库，并内嵌持仓 JSON（先写到 holdings.json）：
  - 7:30 JST，cron 写 `30 22 * * 0-4`（UTC）
  - 9:30 JST，cron 写 `30 0 * * 1-5`（UTC）

  两个 routine 的 prompt 都是：安装 requirements，运行 `python -m bnf premarket`（9:30 那个换成 `postopen`）；stdout 非空就用 PushNotification 原样发出，为空就什么都不做。
- [ ] **Step 4**：两个 routine 各手动触发一次，确认手机收到推送，或者确认按规则应该不发的时候确实没发。
- [ ] **Step 5**：commit `docs: holdings workflow`，然后 push。把两个 routine 的 ID 记进记忆 `bnf-japan-strategy.md`。
