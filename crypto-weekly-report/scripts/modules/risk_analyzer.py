"""
AI 风险分析模块
- 识别宏观/链上/监管/安全风险事件
- 从今日真实新闻中动态提取具体描述（拒绝死板模板）
- 综合新闻和宏观数据判断"川普信号"
"""
import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────

def _compile_regex(keywords: List[str]) -> re.Pattern:
    """将关键词列表编译为不区分大小写的正则（带单词边界，防止误报）"""
    escaped_kw = [re.escape(kw) for kw in keywords]
    # \b 确保匹配单词边界，避免 "button" 触发 "ton" 之类的误报
    return re.compile(r"\b(" + "|".join(escaped_kw) + r")\b", re.IGNORECASE)


def _flat_news(news_by_category: Dict) -> tuple[List[Dict], str]:
    """扁平化所有新闻，返回(items列表, 拼接文本)"""
    items = []
    texts = []
    for category, item_list in news_by_category.items():
        for item in item_list:
            items.append(item)
            texts.append(f"{item.get('title', '')} {item.get('summary', '')}")
    return items, " ".join(texts).lower()


def _extract_dynamic_desc(
    items: List[Dict], regex: re.Pattern, default_desc: str
) -> str:
    """
    从今日含有关键词的真实新闻中抽取具体事件描述。
    优先用真实标题，拒绝空洞模板。
    """
    for item in items:
        title = item.get("title", "")
        summary = item.get("summary", "")
        combined = f"{title} {summary}"
        if regex.search(combined):
            # 截取前60字，保持紧凑可读
            return f"{title[:60]}..." if len(title) > 60 else title
    return default_desc


# ─────────────────────────────────────────────────────
# 扩展后的 Crypto & 宏观风险模式定义
# ─────────────────────────────────────────────────────
RISK_PATTERNS = [
    # 1. 安全与黑客风险（Crypto 核心，优先级最高）
    {
        "key": "security_hack",
        "trigger_keywords": [
            "hack", "exploit", "attack", "drained", "vulnerability",
            "rug pull", "phishing", "breach", "stolen", "funds lost",
        ],
        "default_desc": "链上协议或交易所遭遇安全漏洞/黑客攻击",
        "emoji": "🚨",
        "severity": "critical",
    },
    # 2. 链上与流动性清算风险
    {
        "key": "onchain_liquidation",
        "trigger_keywords": [
            "liquidation cascade", "whale deposit", "dumping",
            "gas spike", "insolvency", "mass liquidation",
            "liquidated", "forced liquidation",
        ],
        "default_desc": "链上大额抛压或面临连锁清算风险",
        "emoji": "⚠️",
        "severity": "high",
    },
    # 3. 稳定币脱锚风险
    {
        "key": "stablecoin",
        "trigger_keywords": [
            "depeg", "usdt", "usdc", "tether",
            "circle stablecoin", "regulatory pressure on usdt",
        ],
        "default_desc": "稳定币流动性或锚定出现异常波动",
        "emoji": "🚨",
        "severity": "critical",
    },
    # 4. 监管与司法诉讼风险
    {
        "key": "crypto_regulatory",
        "trigger_keywords": [
            "sec sue", "cftc", "ban crypto", "crackdown",
            "subpoena", "enforcement action", "complaint",
            "charged", "indicted", "dos", "禁止",
        ],
        "default_desc": "监管机构政策收紧或发起司法诉讼风险",
        "emoji": "⚠️",
        "severity": "high",
    },
    # 5. 美联储鹰派压制流动性
    {
        "key": "fed_hawkish",
        "trigger_keywords": [
            "hawkish", "rate hike", "higher for longer",
            "no cut", "powell hawkish", "拒绝降息",
        ],
        "default_desc": "美联储维持强硬鹰派立场，压制风险资产流动性",
        "emoji": "⚠️",
        "severity": "medium",
    },
    # 6. 美债收益率过高
    {
        "key": "bond_yield",
        "trigger_keywords": [
            "30y", "30-year", "treasury yield", "bond yield",
            "yield above", "收益率突破",
        ],
        "default_desc": "30Y 美债收益率触及关键水平，流动性收紧压力加剧",
        "emoji": "⚠️",
        "severity": "medium",
    },
    # 7. 地缘政治冲突
    {
        "key": "geopolitical",
        "trigger_keywords": [
            "iran", "middle east", "war", "escalation",
            "military action", "中东", "战争", "冲突升级",
        ],
        "default_desc": "地缘政治冲突升级，避险情绪可能引发风险资产回撤",
        "emoji": "⚠️",
        "severity": "medium",
    },
    # 8. 宏观恐慌蔓延
    {
        "key": "market_crash",
        "trigger_keywords": [
            "flash crash", "market panic", "systemic risk",
            "crash", "崩盘", "暴跌",
        ],
        "default_desc": "市场出现恐慌性抛售信号，注意连锁清算风险",
        "emoji": "🚨",
        "severity": "critical",
    },
    # 9. ETF / 机构资金异动（重大流出）
    {
        "key": "etf_outflow",
        "trigger_keywords": [
            "etf outflow", "etf drain", "etf redemption",
            "institutional outflow", "funds outflow",
            "gbTC", "ibit outflow",
        ],
        "default_desc": "现货 ETF 出现大幅净流出，机构看空信号需警惕",
        "emoji": "⚠️",
        "severity": "medium",
    },
    # 10. 关税/贸易战宏观冲击
    {
        "key": "tariff_tradewar",
        "trigger_keywords": [
            "tariff", "trade war", "sanction",
            "关税", "贸易战", "制裁",
        ],
        "default_desc": "关税或贸易摩擦升温，宏观风险偏好大幅降温",
        "emoji": "⚠️",
        "severity": "high",
    },
]

# 川普/政策情绪关键词（短语边界更精确）
TRUMP_BULLISH_KW = [
    "strategic reserve", "btc reserve", "pro-crypto",
    "bitcoin act", "deregulation", "crypto friendly",
    "trump signs", "executive order bitcoin", "bitcoin policy",
]
TRUMP_BEARISH_KW = [
    "tariff", "trade war", "crypto ban", "government sells btc",
    "silk road btc move", "trump tariff", "anti-crypto",
    "sec crackdown", "ban crypto",
]


# ─────────────────────────────────────────────────────
# 核心分析函数
# ─────────────────────────────────────────────────────

def analyze_risks(news_by_category: Dict, macro: Dict) -> Dict:
    """
    分析当前 Crypto 及宏观风险，返回结构化报告:
    {
      risks:        [{"desc": ..., "emoji": ..., "severity": ...}],
      trump_signal: {"label": "看涨"|"看跌"|"中性", "emoji": ..., "detail": ...},
      risk_level:   "low"|"medium"|"high"|"critical",
    }
    """
    items, full_text = _flat_news(news_by_category)

    detected_risks = []
    seen_desc: set = set()

    # 1. 文本风险事件检测（正则 + 动态描述）
    for pattern in RISK_PATTERNS:
        regex = _compile_regex(pattern["trigger_keywords"])
        if regex.search(full_text):
            dynamic_desc = _extract_dynamic_desc(
                items, regex, pattern["default_desc"]
            )
            # 去重（按描述文本）
            if dynamic_desc not in seen_desc:
                seen_desc.add(dynamic_desc)
                detected_risks.append({
                    "desc":     dynamic_desc,
                    "emoji":    pattern["emoji"],
                    "severity": pattern["severity"],
                })

    # 2. 宏观硬指标补充风险
    # 美债 30Y
    us30y = macro.get("us30y") or {}
    if us30y.get("price", 0) >= 5.0:
        desc = f"30Y 美债收益率攀升至 {us30y['price']:.2f}%，无风险利率过高压制风险资产"
        if desc not in seen_desc:
            seen_desc.add(desc)
            detected_risks.append({
                "desc":     desc,
                "emoji":    "⚠️",
                "severity": "high",
            })

    # VIX 恐慌指数
    vix = macro.get("vix") or {}
    if vix.get("price", 0) > 25:
        desc = f"VIX 恐慌指数触及 {vix['price']:.1f}，传统机构避险情绪蔓延至 Crypto"
        if desc not in seen_desc:
            seen_desc.add(desc)
            detected_risks.append({
                "desc":     desc,
                "emoji":    "⚠️",
                "severity": "medium",
            })

    # 原油单日暴涨
    oil = macro.get("oil")
    if oil and oil.get("change_pct", 0) > 3.0:
        desc = f"原油单日暴涨 +{oil['change_pct']:.1f}%，通胀预期急剧升温"
        if desc not in seen_desc:
            seen_desc.add(desc)
            detected_risks.append({
                "desc":     desc,
                "emoji":    "⚠️",
                "severity": "medium",
            })

    # 3. 综合风险等级判定
    severities = [r["severity"] for r in detected_risks]
    if "critical" in severities:
        risk_level = "critical"
    elif severities.count("high") >= 2:
        risk_level = "high"
    elif detected_risks:
        risk_level = "medium"
    else:
        risk_level = "low"

    # 4. 川普/政治情绪判定（先确认 Trump 是否被提及）
    trump_signal = {"label": "中性", "emoji": "⚪", "detail": "市场未见明显政治核心动向"}

    if "trump" in full_text:
        bull_score = sum(
            1 for kw in TRUMP_BULLISH_KW
            if _compile_regex([kw]).search(full_text)
        )
        bear_score = sum(
            1 for kw in TRUMP_BEARISH_KW
            if _compile_regex([kw]).search(full_text)
        )
        if bull_score > bear_score:
            trump_signal = {
                "label":  "看涨",
                "emoji":  "🟢",
                "detail": "川普/政策面释放加密利好或放开监管信号",
            }
        elif bear_score > bull_score:
            trump_signal = {
                "label":  "看跌",
                "emoji":  "🔴",
                "detail": "注意潜在的关税或政府抛售压制信号",
            }
        else:
            trump_signal = {
                "label":  "中性",
                "emoji":  "⚪",
                "detail": "川普相关内容存在，但利好/利空信号相当",
            }

    return {
        "risks":        detected_risks,
        "trump_signal": trump_signal,
        "risk_level":   risk_level,
    }


def format_risk_section(risk_analysis: Dict) -> str:
    """生成今日风险 Markdown 文本（按严重程度排序，最多 5 条）"""
    risks = risk_analysis.get("risks", [])
    if not risks:
        return "· ✅ 今日宏观与链上未见明显极端风险事件，市场情绪相对平稳。"

    # 按严重程度排序（critical > high > medium > low）
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_risks = sorted(
        risks, key=lambda r: severity_order.get(r["severity"], 9)
    )

    lines = []
    for r in sorted_risks[:5]:
        lines.append(f"· {r['emoji']} 风险事件: {r['desc']}")

    return "\n".join(lines)
