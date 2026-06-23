"""
报告渲染模块
将所有数据组装成完整的「AI 加密日报」Markdown 文本
"""
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))


def _fmt_price(price: float, symbol: str = "BTC") -> str:
    """格式化价格（BTC 整数位，ETH/BNB 保留小数）"""
    if symbol in ("BTC",) or price > 10000:
        return f"${price:,.0f}"
    elif price > 100:
        return f"${price:,.0f}"
    else:
        return f"${price:,.2f}"


def _fmt_pct(pct: float) -> str:
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _fmt_sr(levels: list, symbol: str) -> str:
    """格式化支撑/阻力价位列表"""
    return " / ".join(_fmt_price(lv, symbol) for lv in levels)


def _fmt_zone(zone: dict, symbol: str) -> str:
    """格式化增强支撑/压力区间。"""
    low = float(zone.get("low", 0.0))
    high = float(zone.get("high", 0.0))
    score = int(zone.get("score", 0))
    distance_pct = float(zone.get("distance_pct", 0.0))
    interval = " / ".join(zone.get("timeframes", [])) or "—"
    return (
        f"{_fmt_price(low, symbol)}–{_fmt_price(high, symbol)}"
        f"（分{score}，距现价{distance_pct:+.2f}%，{interval}）"
    )


def _rr_star(rr: float, is_primary: bool) -> str:
    """高 R/R 加星"""
    star = " ⭐" if is_primary and rr >= 1.3 else ""
    return f"（R/R {rr:.2f}）{star}"


# ─────────────────────────────────────────────────────
# 第一节：市场总览（单个币种）
# ─────────────────────────────────────────────────────

def _render_coin_section(data: dict) -> str:
    coin     = data["coin"]
    ticker   = data["ticker"]
    ta       = data["ta"]
    sr       = data["sr"]

    symbol   = coin["symbol"]
    emoji    = coin["emoji"]
    price    = ticker["price"]
    chg      = ticker["change_pct"]
    chg_str  = _fmt_pct(chg)
    pr_str   = _fmt_price(price, symbol)

    resistances = sr["resistance"]
    supports    = sr["support"]
    res_str = _fmt_sr(resistances[:2], symbol) if resistances else "—"
    sup_str = _fmt_sr(supports[:2],    symbol) if supports    else "—"

    lines = [
        f"{emoji} **{symbol}** {pr_str}｜24h {chg_str}",
        f"阻力：{res_str}",
        f"支撑：{sup_str}",
    ]

    sr_zones = data.get("sr_zones")
    if sr_zones:
        min_score = int(sr_zones.get("min_score", 0))
        resistance_zones = [
            zone for zone in sr_zones.get("resistance_zones", [])
            if int(zone.get("score", 0)) >= min_score
        ]
        support_zones = [
            zone for zone in sr_zones.get("support_zones", [])
            if int(zone.get("score", 0)) >= min_score
        ]
        if resistance_zones:
            lines.append(f"强压区：{_fmt_zone(resistance_zones[0], symbol)}")
        if support_zones:
            lines.append(f"强支区：{_fmt_zone(support_zones[0], symbol)}")

    lines.extend([
        f"{ta['summary']}",
        "",
    ])
    return "\n".join(lines)


# ─────────────────────────────────────────────────────
# 第二节：宏观流动性
# ─────────────────────────────────────────────────────

def _render_macro_section(macro: dict, risk_analysis: dict) -> str:
    parts = []

    g = macro.get("gold")
    if g:
        parts.append(f"黄金 ${g['price']:,.0f}（{_fmt_pct(g['change_pct'])}）")

    o = macro.get("oil")
    if o:
        parts.append(f"原油 ${o['price']:.2f}（{_fmt_pct(o['change_pct'])}）")

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

    macro_line = "📊 " + " | ".join(parts) if parts else "📊 数据获取中..."

    # 川普信号
    ts = risk_analysis.get("trump_signal", {})
    trump_line = f"\n🇺🇸 川普信号：{ts.get('emoji','⚪')} {ts.get('label','中性')}（{ts.get('detail','')}）"

    # 主要风险事件（最多 3 条）
    risks = risk_analysis.get("risks", [])
    risk_lines = []
    if risks:
        risk_lines.append("")
        for r in risks[:3]:
            risk_lines.append(f"⚠️ {r['desc']}")

    lines = [macro_line, trump_line] + risk_lines
    return "\n".join(lines)


# ─────────────────────────────────────────────────────
# 第三节：要闻速递
# ─────────────────────────────────────────────────────

def _render_news_section(news: dict) -> str:
    lines = []
    icons = {
        "宏观": "🌍 **宏观**",
        "监管": "🏛 **监管**",
        "市场": "📰 **市场**",
        "链上": "🔗 **链上**",
    }

    for cat, icon in icons.items():
        items = news.get(cat, [])
        if not items:
            continue
        lines.append(icon)
        for item in items:
            title  = item["title"]
            source = item.get("source", "")
            lines.append(f"· {title}（{source}）")
        lines.append("")

    return "\n".join(lines).strip() if lines else "· 暂无最新要闻"


# ─────────────────────────────────────────────────────
# 第四节：Twitter 热点
# ─────────────────────────────────────────────────────

def _render_twitter_section(tweets: list) -> str:
    if not tweets:
        return "· 暂无 Twitter 热点数据"
    lines = []
    for t in tweets:
        lines.append(f"· {t['username']}：{t['text']}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────
# 第五节：策略
# ─────────────────────────────────────────────────────

def _render_strategy_coin(data: dict) -> str:
    coin     = data["coin"]
    strategy = data["strategy"]
    ta       = data["ta"]

    symbol   = coin["symbol"]
    emoji    = coin["emoji"]
    bias     = strategy["bias"]
    bull_pct = strategy["bull_pct"]
    bear_pct = strategy["bear_pct"]
    summary  = ta["summary"]

    long_s  = strategy["long"]
    short_s = strategy["short"]

    def entry_str(s, sym):
        return f"{_fmt_price(s['entry_low'], sym)}–{_fmt_price(s['entry_high'], sym)}"

    lines = [
        f"{emoji} **{symbol} {bias}**（{bull_pct}%偏多 / {bear_pct}%偏空）",
        f"📌 {summary}",
        f"做空：{entry_str(short_s, symbol)} 入场，"
        f"目标 {_fmt_price(short_s['target'], symbol)}，"
        f"止损 {_fmt_price(short_s['stop'], symbol)}"
        f"{_rr_star(short_s['rr'], short_s['is_primary'])}",
        f"做多：{entry_str(long_s, symbol)} 入场，"
        f"目标 {_fmt_price(long_s['target'], symbol)}，"
        f"止损 {_fmt_price(long_s['stop'], symbol)}"
        f"{_rr_star(long_s['rr'], long_s['is_primary'])}",
        "",
    ]
    return "\n".join(lines)


def _render_risk_today(risk_analysis: dict) -> str:
    risks = risk_analysis.get("risks", [])
    if not risks:
        return ""

    lines = ["⚠️ **今日独有风险**"]
    # 按严重程度排序
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_risks = sorted(risks, key=lambda r: severity_order.get(r["severity"], 9))
    for r in sorted_risks[:4]:
        lines.append(f"· {r['emoji']} {r['desc']}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────
# 完整报告组装
# ─────────────────────────────────────────────────────

DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


def render_report(
    coins_data:     list[dict],
    macro:          dict,
    news:           dict,
    tweets:         list,
    risk_analysis:  dict,
) -> str:
    """
    组装完整日报 Markdown 文本
    """
    now_cn = datetime.now(TZ_CN)
    date_str = now_cn.strftime("%Y-%m-%d")
    time_str = now_cn.strftime("%H:%M")

    sections = []

    # ─── 标题 ───
    sections.append(f"**AI加密日报 · {date_str} {time_str} (UTC+8)**")
    sections.append("")

    # ─── 一、市场总览 ───
    sections.append("**一、市场总览**")
    for data in coins_data:
        if data:
            sections.append(_render_coin_section(data))

    # ─── 二、宏观/流动性 ───
    sections.append("**二、宏观 / 流动性**")
    sections.append(_render_macro_section(macro, risk_analysis))
    sections.append("")

    # ─── 三、要闻速递 ───
    sections.append(DIVIDER)
    sections.append("**三、要闻速递**（24h内）")
    sections.append(DIVIDER)
    sections.append("")
    sections.append(_render_news_section(news))
    sections.append("")

    # ─── 四、Twitter 热点 ───
    sections.append("**四、Twitter 热点**")
    sections.append(_render_twitter_section(tweets))
    sections.append("")

    # ─── 五、策略 ───
    sections.append("**五、策略**")
    for data in coins_data:
        if data:
            sections.append(_render_strategy_coin(data))

    # 今日独有风险
    risk_text = _render_risk_today(risk_analysis)
    if risk_text:
        sections.append(risk_text)

    return "\n".join(sections)


def save_report(report_text: str, output_dir: str) -> str:
    """
    保存报告到 output_dir，文件名为 YYYY-MM-DD.md
    返回文件路径
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    now_cn = datetime.now(TZ_CN)
    filename = now_cn.strftime("%Y-%m-%d") + ".md"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_text)

    logger.info(f"报告已保存: {filepath}")
    return filepath
