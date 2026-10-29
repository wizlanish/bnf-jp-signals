"""推送文案（spec 第 4 节）。只给价格和时机，不出现股数建议。"""
from bnf.signals import Advice, PostOpen, Premarket, Row

MAX_ROWS = 15
SWITCH_LABEL = {"OFF": "关闭", "ON": "打开", "CRASH": "崩盘档"}
# 回测：同一天破线数 → (胜率, 平均每笔)
HISTORY = [(1, 3, "43%", "-0.9%"), (4, 10, "57%", "+1.4%"), (11, 30, "65%", "+2.1%"), (31, 10**9, "71%", "+2.9%")]
ACTION = {"SELL_AT_OPEN": "开盘市价卖", "SELL_BEFORE_0803": "8:03前市价卖", "NO_DATA": "无法计算"}


def _p(x: float) -> str:
    return f"{x:,.0f}"


def _label(code: str, name: str) -> str:
    return code if not name or name == code else f"{code} {name[:14]}"


def _truncate(lines: list[str], total: int) -> list[str]:
    return lines[:MAX_ROWS] + ([f"…共{total}只"] if total > MAX_ROWS else [])


def _volume(r: Row) -> str:
    if r.vol_ratio is None:
        return ""
    return f" {'放量' if r.vol_ratio >= 1 else '缩量'}{r.vol_ratio:.1f}倍"


def _broken_line(r: Row) -> str:
    return (f"{_label(r.code, r.name)}{_volume(r)} 昨收{_p(r.prev_close)} 乖离{r.bias:+.1%}/线{r.T:+.1%} "
            f"一手{r.lot_cost / 10000:.1f}万 → 开盘买（ひと株须8:03前）")


def _holding_line(a: Advice) -> str:
    head = f"{_label(a.code, a.name)} 第{a.day}天"
    if a.action == "NO_DATA":
        return f"{head} 无法计算"
    if a.action == "LIMIT_SELL":
        act = f"限价卖 {_p(a.target)}"
    elif a.action == "WATCH":
        act = f"观望 目标{_p(a.target)}"
    else:
        act = ACTION[a.action]
    return f"{head} {act}（距目标{a.dist:+.1%}）"


def premarket_text(p: Premarket) -> str:
    out = [f"日经 {_p(p.nk_close)}｜乖离 {p.nk_bias:+.1%}｜开关 {SWITCH_LABEL[p.switch]}｜破线 {p.broken_count}/{p.universe_n}"]
    if p.switch != "OFF":
        for lo, hi, win, avg in HISTORY:
            if lo <= p.broken_count <= hi:
                span = f"{lo}~{hi}只" if hi < 10**9 else f"{lo}只以上"
                out.append(f"历史同类（破线{span}）：胜率{win}，平均每笔{avg}")
        if p.broken:
            out.append("【已破线】按放量从高到低排（破线当天量比 1.5~3 倍的回测最好）")
            out += _truncate([_broken_line(r) for r in p.broken], len(p.broken))
        if p.ambush:
            out.append("【埋伏 限价买（一手股适用）】")
            out += _truncate([f"{_label(r.code, r.name)} 限价 {_p(r.trigger)}" for r in p.ambush], len(p.ambush))
    elif p.broken:
        codes = " ".join(r.code for r in p.broken[:MAX_ROWS])
        out.append(f"个股破线 {len(p.broken)} 只（大盘未恐慌，历史上不赚钱）：{codes}")
    if p.holdings:
        out.append("【持仓】")
        out += [_holding_line(a) for a in p.holdings]
    if p.switch == "OFF" and not p.holdings:
        out.append("今天不动")
    out += [f"⚠️ {w}" for w in p.warnings]
    return "\n".join(out)


def postopen_text(po: PostOpen) -> str:
    out = ["【9:30 开盘后】"]
    if po.crashed:
        out.append("开盘砸穿触发价（一手股可马上买；ひと株只能按收盘价成交）：")
        out += _truncate([f"{_label(r.code, r.name)} 现价{_p(last)} ≤ 触发{_p(r.trigger)}" for r, last in po.crashed],
                         len(po.crashed))
    if po.hit:
        out.append("持仓到价（限价卖单大概已成交，请确认）：")
        out += [f"{_label(a.code, a.name)} 今日最高{_p(high)} ≥ 目标{_p(a.target)}" for a, high in po.hit]
    out += [f"⚠️ {w}" for w in po.warnings]
    return "\n".join(out)
