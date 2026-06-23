# Crypto Daily Report

## 用途

这个 Skill 提供一个脱敏后的 AI 加密日报生成器，可抓取公开行情、宏观数据、加密新闻与公开 X/Twitter 热点，生成 Markdown 格式的市场总览、风险提示与多空策略参考。

适用于：

- 生成 BTC / ETH / BNB 等主流币的日报素材
- 聚合公开行情、公开新闻与公开社媒热点
- 输出可保存到本地，也可按环境变量配置推送到企业微信或 Mattermost

> 风险提示：报告仅供研究与信息整理，不构成投资建议。

## 脱敏声明

本目录是从内部项目能力复制出的公开脱敏版本：

- 不包含原项目 `.git`、日志、历史报告、缓存、WorkBuddy memory 或真实配置产物。
- 不包含企业微信 Webhook、Mattermost Webhook、GitHub token、API key、私密 URL。
- Webhook 推送默认关闭，必须显式通过环境变量启用并注入 URL。
- 公开行情和新闻接口均为无需密钥的公开接口。

## 安装

```bash
cd crypto-daily-report
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使用

```bash
cd crypto-daily-report/scripts
python main.py --test      # 测试模式：生成并打印，不保存文件、不推送
python main.py --print     # 生成报告，保存到 reports/ 并打印
python main.py             # 生成报告并保存
```

## 环境变量配置

默认无需任何密钥即可生成报告。可选环境变量如下：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CRYPTO_DAILY_USE_PROXY` | `false` | 是否启用本地代理 |
| `CRYPTO_DAILY_PROXY_URL` | `http://127.0.0.1:7890` | 代理地址 |
| `CRYPTO_DAILY_PUSH_ENABLED` | `false` | 是否启用推送 |
| `CRYPTO_DAILY_PUSH_PROVIDER` | `mattermost` | `mattermost` 或 `wechat` |
| `MATTERMOST_WEBHOOK_URL` | 空 | Mattermost Incoming Webhook URL |
| `MATTERMOST_USERNAME` | `Crypto Daily Bot` | Mattermost 显示名称 |
| `WECOM_WEBHOOK_URL` | 空 | 企业微信机器人 Webhook URL |
| `CRYPTO_DAILY_REPORTS_DIR` | `scripts/reports` | 报告输出目录 |
| `CRYPTO_DAILY_LOGS_DIR` | `scripts/logs` | 日志输出目录 |
| `CRYPTO_DAILY_SR_ZONES_ENABLED` | `true` | 是否展示增强支撑/压力区间 |

示例：

```bash
export CRYPTO_DAILY_PUSH_ENABLED=true
export CRYPTO_DAILY_PUSH_PROVIDER=mattermost
export MATTERMOST_WEBHOOK_URL="https://mattermost.example.invalid/incoming-webhook-placeholder"
python scripts/main.py
```

## 目录结构

```text
crypto-daily-report/
├── SKILL.md
├── README.md
├── requirements.txt
├── .gitignore
└── scripts/
    ├── main.py
    ├── config.py
    └── modules/
        ├── crypto_data.py
        ├── macro_data.py
        ├── mattermost_pusher.py
        ├── news_fetcher.py
        ├── report_renderer.py
        ├── risk_analyzer.py
        ├── support_resistance_zones.py
        ├── twitter_hotspot.py
        └── wechat_pusher.py
```

## 数据来源

- OKX / Binance / CoinGecko：行情与 K 线公开接口
- Alternative.me：恐贪指数公开接口
- Yahoo Finance 非官方公开接口：黄金、原油、DXY 等宏观数据
- NS3 RSS：加密新闻公开 feed
- Nitter / FxTwitter：公开社媒内容抓取，失败时自动降级

## 常见问题

### 没有配置 Webhook 会失败吗？

不会。脱敏版本默认 `CRYPTO_DAILY_PUSH_ENABLED=false`，未配置 Webhook 时不会推送。即使启用推送但未配置 URL，程序也只会记录警告并继续完成报告生成。

### 是否会写入原项目？

不会。本 Skill 是独立副本，输出目录默认在当前 `scripts/` 下，和原始内部项目互不影响。
