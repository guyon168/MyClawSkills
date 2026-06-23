"""
增强支撑/压力区间分析模块。

阶段一目标：只为报告提供高置信区间预览，不改变旧支撑/阻力与策略语义。
输入兼容 fetch_klines() 返回的 list[dict]，不依赖 pandas。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import math


@dataclass
class Level:
    """单个候选价位。"""

    price: float
    source: str
    timeframe: str
    weight: float = 1.0
    volume: float = 0.0
    touches: int = 1


@dataclass
class Zone:
    """聚类后的支撑/压力区间。"""

    low: float
    high: float
    center: float
    score: int
    distance_pct: float
    atr_distance: float
    source_groups: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=list)
    status: str = "valid"

    def to_dict(self) -> dict[str, Any]:
        """转换为报告层可直接消费的 dict。"""
        return {
            "low": round(self.low, 2),
            "high": round(self.high, 2),
            "center": round(self.center, 2),
            "score": int(self.score),
            "distance_pct": round(self.distance_pct, 2),
            "atr_distance": round(self.atr_distance, 2),
            "source_groups": list(self.source_groups),
            "sources": list(self.sources),
            "timeframes": list(self.timeframes),
            "status": self.status,
        }


def _safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换浮点数。"""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(result) or math.isinf(result):
        return default
    return result


def _valid_klines(klines: Optional[list[dict[str, Any]]]) -> list[dict[str, float]]:
    """清洗 K 线，只保留 OHLC 合法数据。"""
    cleaned: list[dict[str, float]] = []
    if not klines:
        return cleaned
    for item in klines:
        open_price = _safe_float(item.get("open"))
        high = _safe_float(item.get("high"))
        low = _safe_float(item.get("low"))
        close = _safe_float(item.get("close"))
        volume = max(_safe_float(item.get("volume")), 0.0)
        if high <= 0 or low <= 0 or close <= 0:
            continue
        if high < low:
            high, low = low, high
        cleaned.append({
            "open": open_price if open_price > 0 else close,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
    return cleaned


def calc_atr(klines: list[dict[str, Any]], period: int = 14) -> float:
    """计算 Wilder ATR。"""
    data = _valid_klines(klines)
    if len(data) < 2:
        return 0.0

    trs: list[float] = []
    for index in range(1, len(data)):
        high = data[index]["high"]
        low = data[index]["low"]
        prev_close = data[index - 1]["close"]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))

    if not trs:
        return 0.0
    seed_count = min(period, len(trs))
    atr = sum(trs[:seed_count]) / seed_count
    for tr_value in trs[seed_count:]:
        atr = (atr * (period - 1) + tr_value) / period
    return float(atr)


def _simple_ma(values: list[float], period: int) -> float:
    """计算简单移动平均。"""
    if not values:
        return 0.0
    count = min(period, len(values))
    return sum(values[-count:]) / count


def _find_swing_levels(klines: list[dict[str, float]], timeframe: str, window: int = 3) -> list[Level]:
    """识别 swing high/low 候选价位。"""
    levels: list[Level] = []
    if len(klines) < window * 2 + 1:
        return levels

    recent_start = max(len(klines) - 80, 0)
    for index in range(window, len(klines) - window):
        high = klines[index]["high"]
        low = klines[index]["low"]
        volume = klines[index]["volume"]
        recency_bonus = 1.25 if index >= recent_start else 1.0

        if all(high >= klines[index - offset]["high"] for offset in range(1, window + 1)) and all(
            high >= klines[index + offset]["high"] for offset in range(1, window + 1)
        ):
            levels.append(Level(high, "swing_high", timeframe, 1.35 * recency_bonus, volume))

        if all(low <= klines[index - offset]["low"] for offset in range(1, window + 1)) and all(
            low <= klines[index + offset]["low"] for offset in range(1, window + 1)
        ):
            levels.append(Level(low, "swing_low", timeframe, 1.35 * recency_bonus, volume))
    return levels


def _find_fibonacci_levels(klines: list[dict[str, float]], timeframe: str) -> list[Level]:
    """基于近段高低点生成 Fibonacci 候选价位。"""
    if len(klines) < 20:
        return []
    recent = klines[-min(120, len(klines)):]
    swing_high = max(k["high"] for k in recent)
    swing_low = min(k["low"] for k in recent)
    price_range = swing_high - swing_low
    if price_range <= 0:
        return []

    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    levels: list[Level] = []
    for ratio in ratios:
        levels.append(Level(swing_high - price_range * ratio, f"fib_{ratio:.3f}", timeframe, 1.05, 0.0))
    return levels


def _find_pivot_levels(klines: list[dict[str, float]], timeframe: str) -> list[Level]:
    """根据上一根完整 K 线计算 Pivot 价位。"""
    if len(klines) < 2:
        return []
    prev = klines[-2]
    high = prev["high"]
    low = prev["low"]
    close = prev["close"]
    pivot = (high + low + close) / 3.0
    r1 = 2.0 * pivot - low
    s1 = 2.0 * pivot - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    return [
        Level(pivot, "pivot", timeframe, 0.95, prev["volume"]),
        Level(r1, "pivot_r1", timeframe, 1.0, prev["volume"]),
        Level(r2, "pivot_r2", timeframe, 0.85, prev["volume"]),
        Level(s1, "pivot_s1", timeframe, 1.0, prev["volume"]),
        Level(s2, "pivot_s2", timeframe, 0.85, prev["volume"]),
    ]


def _find_ma_levels(klines: list[dict[str, float]], timeframe: str) -> list[Level]:
    """生成常用均线候选价位。"""
    closes = [k["close"] for k in klines]
    levels: list[Level] = []
    for period, weight in [(20, 1.05), (50, 1.0), (100, 0.85), (200, 0.75)]:
        if len(closes) >= max(5, period // 2):
            ma_value = _simple_ma(closes, period)
            if ma_value > 0:
                levels.append(Level(ma_value, f"ma{period}", timeframe, weight, 0.0))
    return levels


def _find_volume_profile_levels(klines: list[dict[str, float]], timeframe: str, bins: int = 24) -> list[Level]:
    """简化 Volume Profile：按典型价格分桶，取高成交量节点。"""
    if len(klines) < 20:
        return []
    recent = klines[-min(180, len(klines)):]
    low_price = min(k["low"] for k in recent)
    high_price = max(k["high"] for k in recent)
    if high_price <= low_price:
        return []

    bucket_count = max(8, min(bins, len(recent) // 3 if len(recent) >= 30 else 8))
    bucket_width = (high_price - low_price) / bucket_count
    volumes = [0.0 for _ in range(bucket_count)]

    for candle in recent:
        typical_price = (candle["high"] + candle["low"] + candle["close"]) / 3.0
        bucket_index = int((typical_price - low_price) / bucket_width)
        bucket_index = max(0, min(bucket_count - 1, bucket_index))
        volumes[bucket_index] += candle["volume"]

    ranked = sorted(range(bucket_count), key=lambda i: volumes[i], reverse=True)
    levels: list[Level] = []
    for bucket_index in ranked[:3]:
        if volumes[bucket_index] <= 0:
            continue
        price = low_price + (bucket_index + 0.5) * bucket_width
        levels.append(Level(price, "volume_profile", timeframe, 1.2, volumes[bucket_index]))
    return levels


def _collect_levels(frames: dict[str, list[dict[str, Any]]]) -> tuple[list[Level], float]:
    """收集多来源候选价位，并返回主 ATR。"""
    all_levels: list[Level] = []
    atr_values: list[float] = []

    for timeframe, raw_klines in frames.items():
        klines = _valid_klines(raw_klines)
        if len(klines) < 20:
            continue
        atr = calc_atr(klines)
        if atr > 0:
            atr_values.append(atr)
        all_levels.extend(_find_swing_levels(klines, timeframe))
        all_levels.extend(_find_fibonacci_levels(klines, timeframe))
        all_levels.extend(_find_pivot_levels(klines, timeframe))
        all_levels.extend(_find_ma_levels(klines, timeframe))
        all_levels.extend(_find_volume_profile_levels(klines, timeframe))

    main_atr = atr_values[0] if atr_values else 0.0
    return all_levels, main_atr


def _weighted_center(levels: list[Level]) -> float:
    """计算候选价位的权重中心。"""
    weight_sum = sum(max(level.weight, 0.1) for level in levels)
    if weight_sum <= 0:
        return sum(level.price for level in levels) / len(levels)
    return sum(level.price * max(level.weight, 0.1) for level in levels) / weight_sum


def _score_cluster(levels: list[Level], current_price: float, center: float, atr: float) -> int:
    """对聚类区间评分，范围 0-100。"""
    unique_sources = {level.source for level in levels}
    unique_timeframes = {level.timeframe for level in levels}
    total_weight = sum(level.weight for level in levels)

    touch_score = min(30.0, len(levels) * 5.0 + total_weight * 2.0)
    source_score = min(30.0, len(unique_sources) * 6.0)
    timeframe_score = min(12.0, len(unique_timeframes) * 6.0)

    distance_pct = abs(center - current_price) / current_price * 100.0 if current_price > 0 else 100.0
    distance_score = max(0.0, 18.0 - distance_pct * 2.0)

    volume_values = [level.volume for level in levels if level.volume > 0]
    volume_score = 10.0 if volume_values else 4.0

    raw_score = touch_score + source_score + timeframe_score + distance_score + volume_score
    if atr > 0:
        spread = max(level.price for level in levels) - min(level.price for level in levels)
        if spread <= atr * 0.8:
            raw_score += 5.0
    return int(max(0, min(100, round(raw_score))))


def _cluster_levels(
    levels: list[Level],
    current_price: float,
    atr: float,
    side: str,
    min_score: int,
) -> list[Zone]:
    """将候选价位按 ATR/价格容差聚类为区间。"""
    if current_price <= 0:
        return []
    filtered = [level for level in levels if (level.price < current_price if side == "support" else level.price > current_price)]
    if not filtered:
        return []

    tolerance = max(atr * 0.7 if atr > 0 else 0.0, current_price * 0.004)
    zone_padding = max(atr * 0.25 if atr > 0 else 0.0, current_price * 0.0015)
    filtered.sort(key=lambda level: level.price)

    clusters: list[list[Level]] = []
    current_cluster: list[Level] = [filtered[0]]
    current_center = filtered[0].price
    for level in filtered[1:]:
        if abs(level.price - current_center) <= tolerance:
            current_cluster.append(level)
            current_center = _weighted_center(current_cluster)
        else:
            clusters.append(current_cluster)
            current_cluster = [level]
            current_center = level.price
    clusters.append(current_cluster)

    zones: list[Zone] = []
    for cluster in clusters:
        center = _weighted_center(cluster)
        low = min(level.price for level in cluster) - zone_padding
        high = max(level.price for level in cluster) + zone_padding
        if side == "support" and high >= current_price:
            high = min(high, current_price * 0.999)
        if side == "resistance" and low <= current_price:
            low = max(low, current_price * 1.001)
        if high <= low:
            continue

        score = _score_cluster(cluster, current_price, center, atr)
        if score < min_score:
            continue
        sources = sorted({level.source for level in cluster})
        source_groups = sorted({level.source.split("_")[0] for level in cluster})
        timeframes = sorted({level.timeframe for level in cluster})
        distance_pct = (center - current_price) / current_price * 100.0
        atr_distance = abs(center - current_price) / atr if atr > 0 else 0.0
        zones.append(Zone(
            low=low,
            high=high,
            center=center,
            score=score,
            distance_pct=distance_pct,
            atr_distance=atr_distance,
            source_groups=source_groups,
            sources=sources,
            timeframes=timeframes,
            status="valid",
        ))

    if side == "support":
        zones.sort(key=lambda zone: (zone.score, zone.center), reverse=True)
    else:
        zones.sort(key=lambda zone: (zone.score, -zone.center), reverse=True)
    return zones


def analyze_zones_from_klines(
    frames: dict[str, list[dict[str, Any]]],
    main_interval: str,
    current_price: float,
    top_n: int = 1,
    min_score: int = 60,
) -> dict[str, Any]:
    """从 K 线集合分析增强支撑/压力区间。

    Args:
        frames: {interval: fetch_klines 返回列表}，可包含单周期或多周期。
        main_interval: 主分析周期。
        current_price: 当前价格。
        top_n: 每侧输出最多区间数。
        min_score: 最低展示/输出分数。

    Returns:
        dict，包含 support_zones / resistance_zones 与元信息。
    """
    if current_price <= 0:
        return {
            "support_zones": [],
            "resistance_zones": [],
            "main_interval": main_interval,
            "current_price": current_price,
            "status": "invalid_price",
        }

    ordered_frames: dict[str, list[dict[str, Any]]] = {}
    if main_interval in frames:
        ordered_frames[main_interval] = frames[main_interval]
    for interval, klines in frames.items():
        if interval != main_interval:
            ordered_frames[interval] = klines

    levels, atr = _collect_levels(ordered_frames)
    top_count = max(1, int(top_n))
    min_score_value = max(0, min(100, int(min_score)))
    support_zones = _cluster_levels(levels, current_price, atr, "support", min_score_value)[:top_count]
    resistance_zones = _cluster_levels(levels, current_price, atr, "resistance", min_score_value)[:top_count]

    return {
        "support_zones": [zone.to_dict() for zone in support_zones],
        "resistance_zones": [zone.to_dict() for zone in resistance_zones],
        "main_interval": main_interval,
        "current_price": round(current_price, 2),
        "atr": round(atr, 2),
        "min_score": min_score_value,
        "status": "ok",
    }
