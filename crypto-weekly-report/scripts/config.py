"""
AI 加密日报 - 脱敏配置文件。

本公开 Skill 仅保留公开行情/新闻接口与可调参数。Webhook、token、私密 URL
均通过环境变量注入，避免在仓库中保存敏感信息。
"""
from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable with a safe default."""
    raw_value = os.getenv(name, "").strip().lower()
    if not raw_value:
        return default
    return raw_value in {"1", "true", "yes", "y", "on"}


# ─────────────────────────────────────────────
# 代理配置
# ─────────────────────────────────────────────
USE_PROXY = _env_bool("CRYPTO_DAILY_USE_PROXY", False)
PROXY_URL = os.getenv("CRYPTO_DAILY_PROXY_URL", "http://127.0.0.1:7890").strip()
PROXY = {
    "http": PROXY_URL,
    "https": PROXY_URL,
}
PROXIES = PROXY if USE_PROXY and PROXY_URL else None

# ─────────────────────────────────────────────
# 监控币种配置
# ─────────────────────────────────────────────
COINS = [
    {
        "symbol": "BTC",
        "name": "Bitcoin",
        "binance_symbol": "BTCUSDT",
        "coingecko_id": "bitcoin",
        "emoji": "🟠",
        "color": "偏空",
    },
    {
        "symbol": "ETH",
        "name": "Ethereum",
        "binance_symbol": "ETHUSDT",
        "coingecko_id": "ethereum",
        "emoji": "🔵",
        "color": "偏空",
    },
    {
        "symbol": "BNB",
        "name": "BNB",
        "binance_symbol": "BNBUSDT",
        "coingecko_id": "binancecoin",
        "emoji": "🟡",
        "color": "偏多",
    },
]

# ─────────────────────────────────────────────
# API 端点（公开接口，无需 key）
# ─────────────────────────────────────────────
BINANCE_API_BASE = "https://api.binance.com/api/v3"
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"
ALTERNATIVE_ME_URL = "https://api.alternative.me/fng/"

KLINE_INTERVAL_1H = "1h"
KLINE_INTERVAL_4H = "4h"
KLINE_INTERVAL_1D = "1d"
KLINE_LIMIT = 200

# ─────────────────────────────────────────────
# 技术指标参数
# ─────────────────────────────────────────────
EMA_SHORT = 20
EMA_LONG = 50
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
RSI_PERIOD = 14
ATR_PERIOD = 14
SUPPORT_RESISTANCE_LOOKBACK = 50

# ─────────────────────────────────────────────
# 增强支撑/压力区间
# ─────────────────────────────────────────────
SR_ZONES_ENABLED = _env_bool("CRYPTO_DAILY_SR_ZONES_ENABLED", True)
SR_ZONES_INTERVAL = os.getenv("CRYPTO_DAILY_SR_ZONES_INTERVAL", "4h")
SR_ZONES_LIMIT = int(os.getenv("CRYPTO_DAILY_SR_ZONES_LIMIT", "300"))
SR_ZONES_TOP_N = int(os.getenv("CRYPTO_DAILY_SR_ZONES_TOP_N", "1"))
SR_ZONES_MULTI_TIMEFRAME = _env_bool("CRYPTO_DAILY_SR_ZONES_MULTI_TIMEFRAME", False)
SR_ZONES_MIN_SCORE = int(os.getenv("CRYPTO_DAILY_SR_ZONES_MIN_SCORE", "60"))
SR_ZONES_USE_IN_STRATEGY = _env_bool("CRYPTO_DAILY_SR_ZONES_USE_IN_STRATEGY", False)

# ─────────────────────────────────────────────
# 策略参数
# ─────────────────────────────────────────────
ENTRY_RANGE_RATIO = float(os.getenv("CRYPTO_DAILY_ENTRY_RANGE_RATIO", "0.004"))
TARGET_ATR_MULT = float(os.getenv("CRYPTO_DAILY_TARGET_ATR_MULT", "1.5"))
STOP_ATR_MULT = float(os.getenv("CRYPTO_DAILY_STOP_ATR_MULT", "1.0"))

# ─────────────────────────────────────────────
# 新闻来源 — NS3 Crypto News Intelligence
# ─────────────────────────────────────────────
NS3_API_BASE = "https://api.ns3.ai/feed"
NS3_LANG = os.getenv("CRYPTO_DAILY_NS3_LANG", "zh-CN")
MAX_NEWS_PER_CATEGORY = int(os.getenv("CRYPTO_DAILY_MAX_NEWS_PER_CATEGORY", "4"))

# ─────────────────────────────────────────────
# Twitter / X 热点来源（公开账号列表）
# ─────────────────────────────────────────────
TWITTER_KOLS = [
    "@PeterLBrandt",
    "@rektcapital",
    "@CryptoCred",
    "@glassnode",
    "@woonomic",
    "@WClementeIII",
    "@DocumentingBTC",
    "@BTC_Archive",
    "@APompliano",
    "@michaelsaylor",
]

# ─────────────────────────────────────────────
# Webhook 推送配置（脱敏：必须通过环境变量注入）
# ─────────────────────────────────────────────
PUSH_ENABLED = _env_bool("CRYPTO_DAILY_PUSH_ENABLED", False)
PUSH_PROVIDER = os.getenv("CRYPTO_DAILY_PUSH_PROVIDER", "mattermost").strip().lower()

WECHAT_WEBHOOK = os.getenv("WECOM_WEBHOOK_URL", "").strip()
MATTERMOST_WEBHOOK = os.getenv("MATTERMOST_WEBHOOK_URL", "").strip()
MATTERMOST_USERNAME = os.getenv("MATTERMOST_USERNAME", "Crypto Daily Bot").strip()

# 兼容旧配置：旧代码读取 WECHAT_PUSH_ENABLED 时仍可工作
WECHAT_PUSH_ENABLED = PUSH_ENABLED

# ─────────────────────────────────────────────
# 输出配置
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.getenv("CRYPTO_DAILY_REPORTS_DIR", os.path.join(BASE_DIR, "reports"))
LOGS_DIR = os.getenv("CRYPTO_DAILY_LOGS_DIR", os.path.join(BASE_DIR, "logs"))
REPORT_HOUR = int(os.getenv("CRYPTO_DAILY_REPORT_HOUR", "7"))
REQUEST_TIMEOUT = int(os.getenv("CRYPTO_DAILY_REQUEST_TIMEOUT", "15"))
REQUEST_DELAY = float(os.getenv("CRYPTO_DAILY_REQUEST_DELAY", "0.5"))
