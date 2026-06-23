"""
宏观数据模块
获取：黄金、原油、美元指数(DXY)、恐贪指数、BTC 主导率、总加密市值
数据来源：CoinGecko（加密）、yfinance/Alpha Vantage(传统)、Alternative.me(恐贪)
"""
import sys
import os
import time
import logging
import requests
from typing import Optional

# 读取代理配置
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import PROXIES
except ImportError:
    PROXIES = None

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15


def _get(url: str, params: dict = None, headers: dict = None, timeout: int = REQUEST_TIMEOUT):
    """带重试 GET（自动携带代理，最多 2 次）"""
    for attempt in range(2):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout, proxies=PROXIES)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug(f"[macro._get] attempt={attempt+1} url={url} err={e}")
            if attempt < 1:
                time.sleep(1)
    return None


# ─────────────────────────────────────────────────────
# 恐贪指数（Alternative.me）
# ─────────────────────────────────────────────────────

def fetch_fear_greed() -> Optional[dict]:
    """
    返回 dict: value(0-100), value_classification, label
    """
    data = _get("https://api.alternative.me/fng/", {"limit": 1, "format": "json"})
    if not data or "data" not in data:
        return None
    item = data["data"][0]
    val = int(item["value"])
    label = item["value_classification"]
    # 中文分类
    cn_map = {
        "Extreme Fear": "极度恐慌",
        "Fear": "恐慌",
        "Neutral": "中性",
        "Greed": "贪婪",
        "Extreme Greed": "极度贪婪",
    }
    return {
        "value": val,
        "label": cn_map.get(label, label),
        "label_en": label,
    }


# ─────────────────────────────────────────────────────
# CoinGecko：BTC 主导率、总市值
# ─────────────────────────────────────────────────────

def fetch_global_crypto() -> Optional[dict]:
    """
    从 CoinGecko 全球接口获取：
    - 总市值 (USD)
    - 24h 市值变化
    - BTC 主导率
    """
    data = _get("https://api.coingecko.com/api/v3/global")
    if not data or "data" not in data:
        return None
    d = data["data"]
    total_mcap = d.get("total_market_cap", {}).get("usd", 0)
    mcap_change = d.get("market_cap_change_percentage_24h_usd", 0)
    btc_dominance = d.get("market_cap_percentage", {}).get("btc", 0)
    eth_dominance = d.get("market_cap_percentage", {}).get("eth", 0)

    return {
        "total_mcap":    total_mcap,
        "mcap_change":   round(mcap_change, 2),
        "btc_dominance": round(btc_dominance, 1),
        "eth_dominance": round(eth_dominance, 1),
    }


# ─────────────────────────────────────────────────────
# Yahoo Finance（yfinance 不需要 key，但通过非官方接口）
# 获取黄金(GC=F)、原油(CL=F)、DXY(DX-Y.NYB)
# ─────────────────────────────────────────────────────

def _fetch_yahoo_quote(ticker_symbol: str) -> Optional[dict]:
    """
    使用 Yahoo Finance v8 API 获取实时报价
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    params = {
        "interval": "1d",
        "range":    "5d",
        "events":   "div,splits",
    }
    data = _get(url, params=params, headers=headers)
    if not data:
        return None

    try:
        result = data["chart"]["result"][0]
        meta = result["meta"]
        current = meta.get("regularMarketPrice") or meta.get("previousClose")
        prev    = meta.get("chartPreviousClose") or meta.get("previousClose")
        if current and prev:
            change_pct = (current - prev) / prev * 100
        else:
            change_pct = 0.0

        return {
            "price":      round(float(current), 2),
            "change_pct": round(float(change_pct), 2),
            "prev_close": round(float(prev), 2) if prev else None,
        }
    except (KeyError, IndexError, TypeError) as e:
        logger.warning(f"解析 Yahoo {ticker_symbol} 失败: {e}")
        return None


def fetch_gold() -> Optional[dict]:
    """黄金现货 / 期货 (GC=F)"""
    result = _fetch_yahoo_quote("GC=F")
    if result:
        result["name"] = "黄金"
        result["unit"] = "USD/oz"
    return result


def fetch_oil() -> Optional[dict]:
    """原油期货 WTI (CL=F)"""
    result = _fetch_yahoo_quote("CL=F")
    if result:
        result["name"] = "WTI 原油"
        result["unit"] = "USD/barrel"
    return result


def fetch_dxy() -> Optional[dict]:
    """美元指数 DXY (DX-Y.NYB)"""
    result = _fetch_yahoo_quote("DX-Y.NYB")
    if not result:
        # 尝试备用 ticker
        result = _fetch_yahoo_quote("UUP")
    if result:
        result["name"] = "DXY"
        result["unit"] = "指数"
    return result


def fetch_us30y_yield() -> Optional[dict]:
    """30 年期美债收益率 (^TYX)"""
    result = _fetch_yahoo_quote("^TYX")
    if result:
        result["name"] = "30Y 美债收益率"
        result["unit"] = "%"
    return result


def fetch_sp500() -> Optional[dict]:
    """标普 500 (^GSPC)"""
    result = _fetch_yahoo_quote("^GSPC")
    if result:
        result["name"] = "标普500"
    return result


def fetch_nasdaq() -> Optional[dict]:
    """纳斯达克 (^IXIC)"""
    result = _fetch_yahoo_quote("^IXIC")
    if result:
        result["name"] = "纳指"
    return result


def fetch_vix() -> Optional[dict]:
    """VIX 恐慌指数 (^VIX)"""
    result = _fetch_yahoo_quote("^VIX")
    if result:
        result["name"] = "VIX"
    return result


# ─────────────────────────────────────────────────────
# 组合获取所有宏观数据
# ─────────────────────────────────────────────────────

def fetch_all_macro() -> dict:
    """
    一次性获取所有宏观数据，返回 dict
    """
    logger.info("获取宏观数据...")

    macro = {}

    macro["fear_greed"] = fetch_fear_greed()
    macro["crypto_global"] = fetch_global_crypto()

    time.sleep(0.3)
    macro["gold"]     = fetch_gold()
    time.sleep(0.3)
    macro["oil"]      = fetch_oil()
    time.sleep(0.3)
    macro["dxy"]      = fetch_dxy()
    time.sleep(0.3)
    macro["us30y"]    = fetch_us30y_yield()
    time.sleep(0.3)
    macro["sp500"]    = fetch_sp500()
    time.sleep(0.3)
    macro["nasdaq"]   = fetch_nasdaq()
    time.sleep(0.3)
    macro["vix"]      = fetch_vix()

    return macro


def format_macro_line(macro: dict) -> str:
    """
    生成宏观摘要单行文字（用于报告第二节）
    """
    parts = []

    g = macro.get("gold")
    if g:
        sign = "+" if g["change_pct"] >= 0 else ""
        parts.append(f"黄金 ${g['price']:,.0f}（{sign}{g['change_pct']:.2f}%）")

    o = macro.get("oil")
    if o:
        sign = "+" if o["change_pct"] >= 0 else ""
        parts.append(f"原油 ${o['price']:.2f}（{sign}{o['change_pct']:.2f}%）")

    d = macro.get("dxy")
    if d:
        parts.append(f"DXY {d['price']:.2f}")

    fg = macro.get("fear_greed")
    if fg:
        parts.append(f"恐贪 {fg['value']} {fg['label']}")

    cg = macro.get("crypto_global")
    if cg:
        parts.append(f"BTC.D {cg['btc_dominance']}%")
        mcap_t = cg["total_mcap"] / 1e12
        parts.append(f"总市值 ${mcap_t:.2f}T")

    return " | ".join(parts)
