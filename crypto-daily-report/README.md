# Crypto Daily Report Skill

脱敏版 AI 加密日报生成器。它基于公开行情、宏观、新闻与公开社媒数据生成 Markdown 市场报告，并支持通过环境变量配置企业微信或 Mattermost 推送。

## 快速运行

```bash
pip install -r requirements.txt
cd scripts
python main.py --test
```

默认不会推送，也不需要任何 API key。若需要推送，请设置 `CRYPTO_DAILY_PUSH_ENABLED=true` 并通过 `MATTERMOST_WEBHOOK_URL` 或 `WECOM_WEBHOOK_URL` 注入 Webhook。

详见 [SKILL.md](./SKILL.md)。
