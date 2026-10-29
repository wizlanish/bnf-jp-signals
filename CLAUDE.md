# bnf-jp-signals

日经 225 乖离率抄底信号，每个东证交易日 7:30 和 9:30（JST）由 GitHub Actions 计算并通过 ntfy 推送到手机（因为 GitHub Actions 会延迟，早上那次实际在 7:10 运行；9:30 那次准点触发、可能晚几分钟）。设计见 `docs/superpowers/specs/`。

## 持仓更新（用户说"买了 / 卖了"时）

**这个仓库是公开的，持仓绝不能写进仓库里的任何文件，也不能提交。**

持仓存在 GitHub Actions 机密 `HOLDINGS_JSON` 里，是一个 JSON 数组。`.github/workflows/push.yml` 运行时把它写成 holdings.json。

JSON 格式：`[{"code": "6273", "shares": 3, "price": 61014, "buy_date": "2026-11-04"}]`

- 用户说"买了 <代码或名称> <股数> <价格>"：加一条，buy_date 取今天（JST）。名称用 `data/names.json` 或 `n225.txt` 换成代码；对不上就问用户。
- 用户说"卖了 …"：删掉对应的那条。同一只股票有多笔时，问用户卖的是哪一笔。
- 机密的值读不回来，所以完整的持仓 JSON 以本机 `~/.bnf-holdings.json` 为准（不在仓库里）。先改这个文件，再在浏览器里打开 https://github.com/wizlanish/bnf-jp-signals/settings/secrets/actions ，更新 `HOLDINGS_JSON`，把整个 JSON 粘进去。
- 改完向用户复述更新后的完整持仓。
- 用户说"同步持仓"：用 moomoo MCP 的 `account_positions`（账户 ID 见用户记忆 moomoo-mcp.md，不要写进本仓库）读出所有 `JP.` 开头的持仓。code 去掉 `JP.`，shares 取 qty，price 取 cost_price，buy_date 取 open_time 换算成 JST 日期。不属于这套策略的持仓要排除，排除名单见用户记忆 bnf-japan-strategy.md（同样不要写进本仓库）。整理好后按上面的方法覆盖本机副本和机密。

推送频道 `NTFY_TOPIC` 也是机密，由用户自己填写，Claude 不要碰。

## 开发

- `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- 测试：`.venv/bin/python -m pytest -q`
- 本地试运行：`.venv/bin/python -m bnf premarket --holdings /path/to/holdings.json`
- 成分股调整后，更新 `n225.txt`，然后删掉 `data/names.json` 并重跑一次，名称会重新缓存。

## 运维

- 定时任务只在 main 分支上生效。
- 公开仓库 60 天没有活动，GitHub 会停掉定时任务。workflow 里有一步保活（每次运行都调用 enable 接口），但还是要偶尔看一下 Actions 页面。
- 运行失败时会推一行"⚠️ bnf 运行失败"，job 也会标红，GitHub 会发邮件。
