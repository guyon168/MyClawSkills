"""
加密货币数据获取 & 技术分析模块
- Binance REST API 获取 OHLCV K 线
- 计算 EMA20/50、MACD、RSI、ATR
- 识别支撑 / 阻力位
- 判断趋势偏向（多/空）及强弱
"""
import sys
import os
import time
import logging
import requests
import numpy as np
from typing import Optional

# 读取代理配置
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import (
        PROXIES,
        SR_ZONES_ENABLED,
        SR_ZONES_INTERVAL,
        SR_ZONES_LIMIT,
        SR_ZONES_TOP_N,
        SR_ZONES_MULTI_TIMEFRAME,
        SR_ZONES_MIN_SCORE,
    )
except ImportError:
    PROXIES = None
    SR_ZONES_ENABLED = False
    SR_ZONES_INTERVAL = "4h"
    SR_ZONES_LIMIT = 300
    SR_ZONES_TOP_N = 1
    SR_ZONES_MULTI_TIMEFRAME = False
    SR_ZONES_MIN_SCORE = 60

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────
# 底层 HTTP 工具
# ─────────────────────────────────────────────────────

def _get(url: str, params: dict = None, timeout: int = 12) -> "dict | list | None":
    """带重试的 GET 请求（自动携带代理）"""
    for attempt in range(2):
        try:
            resp = requests.get(url, params=params, timeout=timeout, proxies=PROXIES)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug(f"[HTTP] attempt={attempt+1} url={url} err={e}")
            if attempt < 1:
                time.sleep(1)
    return None


# ─────────────────────────────────────────────────────
# 多数据源 K 线（自动故障转移）
# ─────────────────────────────────────────────────────

# 数据源优先级（国内可访问优先）
# 映射 symbol -> interval -> OKX 格式
_BINANCE_TO_OKX_INTERVAL = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1H", "4h": "4H", "1d": "1Dutc",
}

# 将 Binance symbol 转换为 OKX instId（BTCUSDT -> BTC-USDT-SWAP / BTC-USDT）
def _binance_to_okx_symbol(binance_symbol: str) -> str:
    """BTCUSDT -> BTC-USDT"""
    # 常见替换
    for quote in ["USDT", "BTC", "ETH", "BNB"]:
        if binance_symbol.endswith(quote):
            base = binance_symbol[: -len(quote)]
            return f"{base}-{quote}"
    return binance_symbol


def _fetch_klines_okx(symbol: str, interval: str, limit: int) -> Optional[list[dict]]:
    """从 OKX 获取 K 线"""
    inst_id = _binance_to_okx_symbol(symbol)
    bar = _BINANCE_TO_OKX_INTERVAL.get(interval, "1Dutc")
    url = "https://www.okx.com/api/v5/market/candles"
    params = {"instId": inst_id, "bar": bar, "limit": str(min(limit, 300))}
    raw = _get(url, params)
    if not raw or raw.get("code") != "0":
        return None
    data_list = raw.get("data", [])
    if not data_list:
        return None
    result = []
    # OKX 返回：[ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
    for k in reversed(data_list):  # OKX 最新在前，需倒序
        try:
            result.append({
                "open_time": int(k[0]),
                "open":  float(k[1]),
                "high":  float(k[2]),
                "low":   float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })
        except (ValueError, IndexError):
            continue
    return result if result else None


def _fetch_klines_coingecko(symbol: str, interval: str, limit: int) -> Optional[list[dict]]:
    """
    从 CoinGecko 获取 K 线（仅日线，作为终极备选）
    symbol: BTCUSDT → bitcoin
    """
    cg_map = {
        "BTCUSDT": "bitcoin",
        "ETHUSDT": "ethereum",
        "BNBUSDT": "binancecoin",
    }
    cg_id = cg_map.get(symbol)
    if not cg_id:
        return None

    # CoinGecko OHLC 接口：/coins/{id}/ohlc?vs_currency=usd&days=N
    days = min(limit, 90)
    url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc"
    params = {"vs_currency": "usd", "days": str(days)}
    raw = _get(url, params)
    if not raw:
        return None
    # 返回 [[timestamp, open, high, low, close], ...]
    result = []
    for k in raw:
        if len(k) >= 5:
            result.append({
                "open_time": int(k[0]),
                "open":  float(k[1]),
                "high":  float(k[2]),
                "low":   float(k[3]),
                "close": float(k[4]),
                "volume": 0.0,  # CoinGecko OHLC 无成交量
            })
    return result if result else None


def _fetch_klines_binance(symbol: str, interval: str, limit: int) -> Optional[list[dict]]:
    """从 Binance 获取 K 线"""
    # 同时尝试 binance.com 和镜像站
    endpoints = [
        "https://api.binance.com/api/v3/klines",
        "https://api1.binance.com/api/v3/klines",
        "https://api.binance.us/api/v3/klines",
    ]
    for url in endpoints:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        raw = _get(url, params, timeout=10)
        if raw and isinstance(raw, list):
            result = []
            for k in raw:
                result.append({
                    "open_time": int(k[0]),
                    "open":  float(k[1]),
                    "high":  float(k[2]),
                    "low":   float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                })
            return result
    return None


def fetch_klines(symbol: str, interval: str = "1d", limit: int = 200) -> Optional[list[dict]]:
    """
    从多数据源获取 K 线（自动故障转移）：
    OKX → Binance → CoinGecko(仅日线)
    """
    # 1. 优先 OKX（国内可直连）
    result = _fetch_klines_okx(symbol, interval, limit)
    if result and len(result) >= 30:
        logger.debug(f"  {symbol} K线来源: OKX ({len(result)} 根)")
        return result

    # 2. 尝试 Binance
    result = _fetch_klines_binance(symbol, interval, limit)
    if result and len(result) >= 30:
        logger.debug(f"  {symbol} K线来源: Binance ({len(result)} 根)")
        return result

    # 3. 日线才能用 CoinGecko
    if interval == "1d":
        result = _fetch_klines_coingecko(symbol, interval, limit)
        if result and len(result) >= 30:
            logger.debug(f"  {symbol} K线来源: CoinGecko ({len(result)} 根)")
            return result

    logger.error(f"所有数据源均无法获取 {symbol} {interval} K线")
    return None


def _fetch_ticker_okx(symbol: str) -> Optional[dict]:
    """OKX 24h 行情"""
    inst_id = _binance_to_okx_symbol(symbol)
    url = "https://www.okx.com/api/v5/market/ticker"
    params = {"instId": inst_id}
    raw = _get(url, params)
    if not raw or raw.get("code") != "0":
        return None
    data = raw.get("data", [{}])[0]
    try:
        last  = float(data["last"])
        open_ = float(data["open24h"])
        chg   = (last - open_) / open_ * 100 if open_ else 0
        return {
            "price":        last,
            "change_pct":   round(chg, 2),
            "high_24h":     float(data.get("high24h", last)),
            "low_24h":      float(data.get("low24h",  last)),
            "volume_24h":   float(data.get("volCcy24h", 0)),
        }
    except (KeyError, ValueError):
        return None


def _fetch_ticker_coingecko(symbol: str) -> Optional[dict]:
    """CoinGecko 行情（备选）"""
    cg_map = {
        "BTCUSDT": "bitcoin",
        "ETHUSDT": "ethereum",
        "BNBUSDT": "binancecoin",
    }
    cg_id = cg_map.get(symbol)
    if not cg_id:
        return None
    url = f"https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": cg_id,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_24hr_vol": "true",
    }
    raw = _get(url, params)
    if not raw or cg_id not in raw:
        return None
    d = raw[cg_id]
    return {
        "price":        float(d.get("usd", 0)),
        "change_pct":   float(d.get("usd_24h_change", 0)),
        "high_24h":     float(d.get("usd", 0)),
        "low_24h":      float(d.get("usd", 0)),
        "volume_24h":   float(d.get("usd_24h_vol", 0)),
    }


def fetch_ticker_24h(symbol: str) -> Optional[dict]:
    """24h 行情（自动故障转移：OKX → Binance → CoinGecko）"""
    # 1. OKX
    result = _fetch_ticker_okx(symbol)
    if result and result["price"] > 0:
        return result

    # 2. Binance
    for base_url in ["https://api.binance.com", "https://api1.binance.com"]:
        url = f"{base_url}/api/v3/ticker/24hr"
        data = _get(url, {"symbol": symbol}, timeout=10)
        if data and "lastPrice" in data:
            return {
                "price":        float(data["lastPrice"]),
                "change_pct":   float(data["priceChangePercent"]),
                "high_24h":     float(data["highPrice"]),
                "low_24h":      float(data["lowPrice"]),
                "volume_24h":   float(data["quoteVolume"]),
            }

    # 3. CoinGecko
    result = _fetch_ticker_coingecko(symbol)
    if result and result["price"] > 0:
        return result

    return None


# ─────────────────────────────────────────────────────
# 技术指标计算
# ─────────────────────────────────────────────────────

def _ema(closes: np.ndarray, period: int) -> np.ndarray:
    """指数移动平均"""
    result = np.zeros_like(closes)
    k = 2.0 / (period + 1)
    result[0] = closes[0]
    for i in range(1, len(closes)):
        result[i] = closes[i] * k + result[i - 1] * (1 - k)
    return result


def calc_ema(klines: list[dict], period: int) -> float:
    """返回最新 EMA 值"""
    closes = np.array([k["close"] for k in klines])
    return float(_ema(closes, period)[-1])


def calc_macd(klines: list[dict],
              fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """
    返回 dict:
      macd_line, signal_line, histogram, cross (golden/dead/none)
    """
    closes = np.array([k["close"] for k in klines])
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line

    # 判断金叉/死叉
    cross = "none"
    if len(histogram) >= 2:
        if histogram[-2] < 0 and histogram[-1] > 0:
            cross = "golden"
        elif histogram[-2] > 0 and histogram[-1] < 0:
            cross = "dead"

    return {
        "macd_line":   float(macd_line[-1]),
        "signal_line": float(signal_line[-1]),
        "histogram":   float(histogram[-1]),
        "cross":       cross,
    }


def calc_rsi(klines: list[dict], period: int = 14) -> float:
    """RSI 指标"""
    closes = np.array([k["close"] for k in klines])
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def calc_atr(klines: list[dict], period: int = 14) -> float:
    """平均真实波幅"""
    trs = []
    for i in range(1, len(klines)):
        h, l, prev_c = klines[i]["high"], klines[i]["low"], klines[i - 1]["close"]
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    if not trs:
        return 0.0
    # Wilder smoothing
    atr = np.mean(trs[:period])
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return float(atr)


# ─────────────────────────────────────────────────────
# 支撑 / 阻力位识别
# ─────────────────────────────────────────────────────

def _cluster_by_volume(
    pivots: list[tuple[float, float]], tolerance: float
) -> list[float]:
    """
    成交量加权聚类：将相近的极值点合并为单一支撑/阻力位。
    pivots: [(价格, 成交量), ...]
    tolerance: 动态容差（使用 ATR）
    """
    if not pivots:
        return []
    pivots = sorted(pivots, key=lambda x: x[0])
    merged = []
    curr_prices: list[float] = [pivots[0][0]]
    curr_vols:   list[float] = [pivots[0][1]]

    for price, vol in pivots[1:]:
        if (price - np.mean(curr_prices)) <= tolerance:
            curr_prices.append(price)
            curr_vols.append(vol)
        else:
            merged.append(float(np.average(curr_prices, weights=curr_vols)))
            curr_prices = [price]
            curr_vols   = [vol]

    if curr_prices:
        merged.append(float(np.average(curr_prices, weights=curr_vols)))
    return merged


def find_support_resistance(
    klines: list[dict], lookback: int = 60, num_levels: int = 3
) -> dict:
    """
    改进版支撑/阻力识别:
    1. 剔除最后一根未收盘K线，保证盘中执行稳定性
    2. ATR 动态容差代替死板 0.5%
    3. 成交量加权聚类融合相邻极值点
    返回 dict: support=[...], resistance=[...]  (从近到远排序)
    """
    if len(klines) < lookback:
        recent = klines[:-1] if len(klines) > 1 else klines
    else:
        # 剔除最后一根（当天未收盘K线），锁死历史极值点
        recent = klines[-lookback:-1]

    if len(recent) < 5:
        recent = klines

    highs   = [k["high"]  for k in recent]
    lows    = [k["low"]   for k in recent]
    volumes = [k["volume"] for k in recent]
    current_price = klines[-1]["close"]

    # 1. 局部极值识别（附带成交量）
    pivot_highs: list[tuple[float, float]] = []
    pivot_lows:  list[tuple[float, float]] = []
    window = 3

    for i in range(window, len(recent) - window):
        h = highs[i]
        if all(h >= highs[i - j] for j in range(1, window + 1)) and \
           all(h >= highs[i + j] for j in range(1, window + 1)):
            pivot_highs.append((h, volumes[i]))

        lo = lows[i]
        if all(lo <= lows[i - j] for j in range(1, window + 1)) and \
           all(lo <= lows[i + j] for j in range(1, window + 1)):
            pivot_lows.append((lo, volumes[i]))

    # 补充最近 10 根 K 线极值（近期价格行为权重更高）
    for k in recent[-10:]:
        pivot_highs.append((k["high"], k["volume"]))
        pivot_lows.append((k["low"],   k["volume"]))

    # 2. ATR 动态容差（波动率自适应）
    atr  = calc_atr(klines, 14)
    tol  = atr if atr > 0 else current_price * 0.006

    # 3. 成交量加权聚类
    resistances = [
        r for r in _cluster_by_volume(pivot_highs, tol)
        if r > current_price
    ]
    supports = [
        s for s in _cluster_by_volume(pivot_lows, tol)
        if s < current_price
    ]

    # 取最近的 num_levels 个
    return {
        "support":    sorted(supports,    reverse=True)[:num_levels],
        "resistance":  sorted(resistances)[:num_levels],
    }


# ─────────────────────────────────────────────────────
# 趋势判断
# ─────────────────────────────────────────────────────

def analyze_trend(klines_1d: list[dict], klines_1h: list[dict]) -> dict:
    """
    改进版多周期趋势分析:
    1. ATR 动态缓冲区，防止价格在均线附近反复横跳导致评分颠簸
    2. 日线大趋势占 70% 权重，1H 日内择时占 30%
    3. 综合多空归一化打分（0~100%）

    返回:
    {
      ema20, ema50, macd, rsi, atr,
      trend_bias: '偏多'|'偏空'|'中性',
      bull_pct, bear_pct,
      summary: 简短描述
    }
    """
    ema20   = calc_ema(klines_1d, 20)
    ema50   = calc_ema(klines_1d, 50)
    macd    = calc_macd(klines_1d)
    rsi     = calc_rsi(klines_1d)
    atr     = calc_atr(klines_1d)
    price   = klines_1d[-1]["close"]
    rsi_1h  = calc_rsi(klines_1h, 14)
    macd_1h = calc_macd(klines_1h)

    # ─── ATR 动态缓冲区 ───
    # 只有当价格偏离 EMA20 超过 0.2 * ATR 时才给完整加减分
    # 否则视为中性（防止均线附近反复横跳导致评分剧烈波动）
    buffer = 0.2 * atr if atr > 0 else price * 0.002

    # ─── 日线大趋势评分（满分 10 分） ───
    macro_score = 0.0

    # 1. 价格 vs EMA20（带缓冲区）
    if price > ema20 + buffer:
        macro_score += 3.0
    elif price < ema20 - buffer:
        macro_score -= 3.0
    # 在缓冲区内不加不减，防止震荡市频繁切换

    # 2. EMA 均线多头/空头排列
    macro_score += 3.0 if ema20 > ema50 else -3.0

    # 3. 日线 MACD
    if macd["cross"] == "golden":
        macro_score += 2.0
    elif macd["cross"] == "dead":
        macro_score -= 2.0
    elif macd["histogram"] > 0:
        macro_score += 1.0
    else:
        macro_score -= 1.0

    # 4. 日线 RSI 强弱
    if rsi > 60:
        macro_score += 2.0
    elif rsi < 40:
        macro_score -= 2.0

    # ─── 1H 日内择时评分（满分 10 分） ───
    micro_score = 0.0

    if macd_1h["histogram"] > 0:
        micro_score += 5.0
    else:
        micro_score -= 5.0

    if rsi_1h > 55:
        micro_score += 5.0
    elif rsi_1h < 45:
        micro_score -= 5.0

    # ─── 综合多空归一化 ───
    # macro: [-10, +10] → [0, 1]
    macro_norm = (macro_score + 10.0) / 20.0
    # micro: [-10, +10] → [0, 1]
    micro_norm = (micro_score + 10.0) / 20.0

    # 日线权重 70%，1H 权重 30%
    final_score = macro_norm * 0.7 + micro_norm * 0.3

    bull_pct = round(final_score * 100)
    bear_pct = 100 - bull_pct

    if bull_pct >= 60:
        trend_bias = "偏多"
    elif bear_pct >= 60:
        trend_bias = "偏空"
    else:
        trend_bias = "中性"

    # ─── 构造描述文字 ───
    parts = []
    if macd["cross"] == "dead":
        parts.append("日线 MACD 死叉")
    elif macd["cross"] == "golden":
        parts.append("日线 MACD 金叉")
    elif macd["histogram"] < 0:
        parts.append("日线 MACD 弱势")

    parts.append(f"RSI {rsi:.1f}")

    if rsi < 30:
        parts.append("接近超卖")
    elif rsi > 70:
        parts.append("接近超买")
    elif rsi < 45:
        parts.append("中性偏弱")
    else:
        parts.append("中性")

    if price < ema20 - buffer:
        parts.append(f"价格压在 EMA20({ema20:,.0f}) 下方")
    elif price > ema20 + buffer:
        parts.append(f"价格站上 EMA20({ema20:,.0f})")
    else:
        parts.append(f"价格在 EMA20({ema20:,.0f}) 附近震荡")

    if macd_1h["histogram"] < 0:
        parts.append("1H 弱势")
    else:
        parts.append("1H 偏强")

    return {
        "ema20":      ema20,
        "ema50":      ema50,
        "macd":       macd,
        "rsi":        rsi,
        "atr":        atr,
        "rsi_1h":     rsi_1h,
        "trend_bias": trend_bias,
        "bull_pct":   bull_pct,
        "bear_pct":   bear_pct,
        "summary":    "，".join(parts),
    }


# ─────────────────────────────────────────────────────
# 策略生成
# ─────────────────────────────────────────────────────

def generate_strategy(coin: dict, ticker: dict, sr: dict, ta: dict) -> dict:
    """
    根据趋势偏向，生成做多/做空方案：
    返回 dict {long: {...}, short: {...}}
    """
    price = ticker["price"]
    atr   = ta["atr"]

    supports    = sr["support"]
    resistances = sr["resistance"]

    # ─── 做多策略 ───
    if supports:
        long_low  = supports[0] * 0.999
        long_high = supports[0] * 1.003
        long_target = resistances[0] if resistances else price * 1.03
        long_stop   = supports[1] if len(supports) > 1 else supports[0] * 0.985
        long_rr = abs(long_target - long_high) / abs(long_high - long_stop) if abs(long_high - long_stop) > 0 else 0
    else:
        long_low, long_high = price * 0.98, price * 0.985
        long_target = price * 1.03
        long_stop = price * 0.97
        long_rr = 1.0

    # ─── 做空策略 ───
    if resistances:
        short_low  = resistances[0] * 0.998
        short_high = resistances[0] * 1.003
        short_target = supports[0] if supports else price * 0.97
        short_stop   = resistances[1] if len(resistances) > 1 else resistances[0] * 1.015
        short_rr = abs(short_high - short_target) / abs(short_stop - short_high) if abs(short_stop - short_high) > 0 else 0
    else:
        short_low, short_high = price * 1.01, price * 1.015
        short_target = price * 0.97
        short_stop = price * 1.025
        short_rr = 1.0

    # 根据趋势偏向决定哪个是主策略（打星号）
    bias = ta["trend_bias"]
    long_star  = (bias == "偏多")
    short_star = (bias == "偏空")

    return {
        "bias":  bias,
        "bull_pct": ta["bull_pct"],
        "bear_pct": ta["bear_pct"],
        "long": {
            "entry_low":  round(long_low,  2),
            "entry_high": round(long_high, 2),
            "target":     round(long_target, 2),
            "stop":       round(long_stop, 2),
            "rr":         round(long_rr, 2),
            "is_primary": long_star,
        },
        "short": {
            "entry_low":  round(short_low,  2),
            "entry_high": round(short_high, 2),
            "target":     round(short_target, 2),
            "stop":       round(short_stop,  2),
            "rr":         round(short_rr, 2),
            "is_primary": short_star,
        },
    }


# ─────────────────────────────────────────────────────
# 主入口：获取单个币种完整分析
# ─────────────────────────────────────────────────────

def analyze_coin(coin: dict) -> Optional[dict]:
    """
    对单个币种执行完整分析，返回分析结果 dict。
    """
    symbol = coin["binance_symbol"]
    logger.info(f"分析 {symbol} ...")

    # K 线
    klines_1d = fetch_klines(symbol, "1d", 200)
    klines_1h = fetch_klines(symbol, "1h", 200)
    ticker    = fetch_ticker_24h(symbol)

    if not klines_1d or not klines_1h or not ticker:
        logger.error(f"获取 {symbol} 数据失败")
        return None

    # 技术分析
    ta = analyze_trend(klines_1d, klines_1h)

    # 支撑/阻力
    sr = find_support_resistance(klines_1d)

    # 阶段一增强支撑/压力区间：仅用于报告展示，不参与旧 sr/strategy。
    sr_zones = None
    if SR_ZONES_ENABLED:
        try:
            from modules.support_resistance_zones import analyze_zones_from_klines

            frames = {}
            sr_interval = SR_ZONES_INTERVAL or "4h"
            if sr_interval == "1d":
                frames[sr_interval] = klines_1d
            elif sr_interval == "1h":
                frames[sr_interval] = klines_1h
            else:
                fetched = fetch_klines(symbol, sr_interval, SR_ZONES_LIMIT)
                if fetched:
                    frames[sr_interval] = fetched

            if SR_ZONES_MULTI_TIMEFRAME:
                frames.setdefault("1d", klines_1d)
                frames.setdefault("1h", klines_1h)

            if frames:
                sr_zones = analyze_zones_from_klines(
                    frames=frames,
                    main_interval=sr_interval,
                    current_price=ticker["price"],
                    top_n=SR_ZONES_TOP_N,
                    min_score=SR_ZONES_MIN_SCORE,
                )
            else:
                logger.warning(f"{symbol} 增强支撑/压力区间无可用K线，已降级跳过")
        except Exception as exc:
            logger.warning(f"{symbol} 增强支撑/压力区间分析失败，已降级跳过: {exc}")
            sr_zones = None

    # 策略
    strategy = generate_strategy(coin, ticker, sr, ta)

    return {
        "coin":     coin,
        "ticker":   ticker,
        "ta":       ta,
        "sr":       sr,
        "sr_zones": sr_zones,
        "strategy": strategy,
    }
