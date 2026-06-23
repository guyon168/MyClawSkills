"""
新闻聚合模块 - NS3 Crypto News Intelligence
使用 NS3 API（https://ns3.ai）获取 AI 分级加密新闻
- Feed 1: News RSS (news-data)  - 实时新闻流，AI 分级 L1-L4
- Feed 2: Top News (news-ranking) - 24h 最重要的 Top 10
- Feed 3: Daily Briefing (today-summary) - 24h 综述简报
- Feed 4: Breaking News (news-flash) - 突发头条
无需 API Key，支持 16 种语言，Binance / CoinGecko 使用此数据
"""
import sys
import os
import re
import time
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import PROXIES
except ImportError:
    PROXIES = None

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# NS3 API 配置
# ═══════════════════════════════════════════════════════════

NS3_BASE = "https://api.ns3.ai/feed"
NS3_LANG = "zh-CN"          # 简体中文（ns3 原生翻译，无需额外翻译）
REQUEST_TIMEOUT = 20
MAX_NEWS_PER_CATEGORY = 4   # 每分类最多条数

# 新闻分类与 NS3 categoryId 映射
# Category IDs: 1=Market Trends, 2=Regulation & Policy, 3=Institutional Updates,
#               4=Market Outlook, 5=General, 6=Exchange & Venue, 7=Macro & Geopolitical, 8=Security & Incidents
NS3_CATEGORY_MAP = {
    "宏观": [7, 1],          # Macro & Geopolitical, Market Trends
    "监管": [2, 3],          # Regulation & Policy, Institutional Updates
    "市场": [1, 3, 4],       # Market Trends, Institutional Updates, Market Outlook
    "链上": [8, 5, 6],       # Security & Incidents, General, Exchange & Venue
}

# 关键词兜底分类（当 category 字段不够精确时）
_KEYWORD_CATS = {
    "宏观": [
        "美联储", "美债", "通胀", "利率", "降息", "加息", "宏观", "经济",
        "美元", "CPI", "GDP", "非农", "国债", "收益率", "鲍威尔", "关税",
        "fed", "rate", "treasury", "inflation", "macro", "yield", "fomc",
        "tariff", "gold", "oil", "dollar",
    ],
    "监管": [
        "监管", "合规", "立法", "法案", "ETF", "审批", "牌照", "证监会",
        "政策", "SEC", "CFTC", "国会", "参议院", "禁令",
        "sec", "regulation", "etf", "approved", "congress", "senate", "ban",
        "clarity act", "legislation", "policy",
    ],
    "市场": [
        "机构", "贝莱德", "富达", "灰度", "主权基金", "上市", "收购", "增持",
        "黑石", "纳斯达克", "标普", "暴跌", "暴涨", "杠杆", "爆仓",
        "blackrock", "fidelity", "grayscale", "nasdaq", "institution",
        "fund", "market", "liquidation", "rally", "crash",
    ],
    "链上": [
        "链上", "鲸鱼", "DeFi", "以太坊", "Solana", "质押", "矿工", "减半",
        "钱包", "跨链桥", "空投", "Gas", "NFT", "智能合约", "DEX",
        "whale", "on-chain", "defi", "staking", "bridge", "protocol",
        "wallet", "mining", "nft", "dao", "gas",
    ],
}


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def _clean_html(text: str) -> str:
    """去除 HTML 标签和多余空白"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_rfc822(date_str: str) -> Optional[datetime]:
    """解析 RFC 822 日期字符串 → UTC datetime"""
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%d %b %Y %H:%M:%S %z",
        "%d %b %Y %H:%M:%S GMT",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _is_recent(pub_date_str: str, max_hours: int = 26) -> bool:
    """判断是否在时效内"""
    dt = _parse_rfc822(pub_date_str)
    if dt is None:
        return True  # 无法解析放行
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_hours)
    return dt >= cutoff


def _deduplicate(items: list[dict]) -> list[dict]:
    """基于标题哈希去重"""
    seen = set()
    result = []
    for item in items:
        key = hashlib.md5(item["title"].lower().strip().encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _classify_news_by_keyword(title: str, summary: str = "") -> str:
    """关键词兜底分类"""
    text = (title + " " + summary).lower()
    best_cat = "市场"
    best_score = 0
    for cat, keywords in _KEYWORD_CATS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > best_score:
            best_score = score
            best_cat = cat
    return best_cat


def _ns3_category_to_local(ns3_cat_id: Optional[int], title: str, summary: str) -> str:
    """
    将 NS3 category ID 映射到本地四分类（宏观/监管/市场/链上）
    如果 category_id 不够精确，再用关键词兜底
    """
    if ns3_cat_id is not None:
        for local_cat, ids in NS3_CATEGORY_MAP.items():
            if ns3_cat_id in ids:
                return local_cat
    return _classify_news_by_keyword(title, summary)


def _fetch_xml(url: str, tag: str = "item") -> list[ET.Element]:
    """
    获取 NS3 RSS XML 并返回所有 <item> 元素列表
    """
    try:
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            proxies=PROXIES,
            headers={"User-Agent": "crypto-daily-bot/1.0", "Accept": "application/xml"},
        )
        resp.raise_for_status()
        # 处理可能的 BOM
        text = resp.content.decode("utf-8-sig")
        root = ET.fromstring(text)

        # 兼容 <rss><channel><item> 和直接 <item>
        items = root.findall(f".//{tag}")
        return items
    except requests.RequestException as e:
        logger.warning(f"NS3 请求失败 {url}: {e}")
        return []
    except ET.ParseError as e:
        logger.warning(f"NS3 XML 解析失败 {url}: {e}")
        return []


def _elem_text(elem: Optional[ET.Element]) -> str:
    """安全取 Element 文本，处理 CDATA"""
    if elem is None:
        return ""
    return (elem.text or "").strip()


def _extract_source_from_insight(insight: str) -> str:
    """从 insight 或 link 中提取来源媒体名"""
    # NS3 link 格式：https://ns3.ai/news/xxxx，无法直接得到原始媒体名
    # 尝试从 insight 中找 "Source:" 标注，否则返回默认值
    match = re.search(r"Source[:：]\s*([^\n\r]+)", insight or "")
    if match:
        return match.group(1).strip()
    return "NS3.ai"


# ═══════════════════════════════════════════════════════════
# Feed 1: News RSS — 实时新闻流（主力数据源）
# ═══════════════════════════════════════════════════════════

def fetch_news_rss(
    lang: str = NS3_LANG,
    limit: int = 40,
    exclude_levels: str = "4",    # 默认排除 L4 常规信息
    crypto: Optional[str] = None, # 指定币种过滤，如 "BTC,ETH"
    news_type: Optional[str] = None,  # "important" / "breaking" / "normal"
) -> list[dict]:
    """
    获取 NS3 实时新闻 RSS（Feed 1）
    返回结构化新闻列表，每项含 title / summary / category / source / level / pub_time
    """
    url = f"{NS3_BASE}/news-data?lang={lang}&limit={limit}"
    if exclude_levels:
        url += f"&excludeLevels={exclude_levels}"
    if crypto:
        url += f"&crypto={crypto}"
    if news_type:
        url += f"&newsType={news_type}"

    logger.debug(f"NS3 News RSS: {url}")
    items_raw = _fetch_xml(url, tag="item")
    if not items_raw:
        return []

    ns = {"media": "http://search.yahoo.com/mrss/"}
    results = []

    for item in items_raw:
        title    = _clean_html(_elem_text(item.find("title")))
        desc     = _clean_html(_elem_text(item.find("description")))
        link     = _elem_text(item.find("link"))
        pub_date = _elem_text(item.find("pubDate"))
        level_el = item.find("level")
        level    = int(_elem_text(level_el)) if level_el is not None and _elem_text(level_el).isdigit() else 3
        news_type_el = item.find("newsType")
        n_type   = _elem_text(news_type_el) if news_type_el is not None else "normal"
        insight  = _elem_text(item.find("insight"))

        # 提取 mentionedCoins
        coins_el = item.find("mentionedCoins")
        mentioned_coins = _elem_text(coins_el) if coins_el is not None else ""

        if not title:
            continue
        if not _is_recent(pub_date):
            continue

        # 从 insight Key Point 中提取摘要（更精炼）
        summary = _extract_key_point(insight) or desc[:200]

        results.append({
            "title":          title,
            "summary":        summary[:200],
            "link":           link,
            "source":         "NS3.ai",
            "pub_time":       pub_date,
            "level":          level,
            "news_type":      n_type,
            "mentioned_coins": mentioned_coins,
            "insight":        insight,
            "category":       _classify_news_by_keyword(title, summary),
        })

    logger.debug(f"NS3 News RSS 获取 {len(results)} 条")
    return results


def _extract_key_point(insight: str) -> str:
    """从 insight 中提取 ## Key Point 章节"""
    if not insight:
        return ""
    match = re.search(r"##\s*Key Point\s*\n+(.*?)(?=##|\Z)", insight, re.DOTALL | re.IGNORECASE)
    if match:
        kp = match.group(1).strip()
        # 取第一段（去掉 "Why it matters" 之后的部分）
        first_para = kp.split("\n\n")[0] if "\n\n" in kp else kp
        return first_para.strip()[:200]
    return ""


# ═══════════════════════════════════════════════════════════
# Feed 2: Top News — 24h 最重要 Top 10（仅 L1/L2）
# ═══════════════════════════════════════════════════════════

def fetch_top_news(lang: str = NS3_LANG) -> list[dict]:
    """
    获取 NS3 Top 10 重要新闻（Feed 2）
    仅包含 L1/L2 级别，按重要性排序
    """
    url = f"{NS3_BASE}/news-ranking?lang={lang}"
    logger.debug(f"NS3 Top News: {url}")
    items_raw = _fetch_xml(url, tag="item")
    if not items_raw:
        return []

    results = []
    for item in items_raw:
        title    = _clean_html(_elem_text(item.find("title")))
        desc     = _clean_html(_elem_text(item.find("description")))
        link     = _elem_text(item.find("link"))
        pub_date = _elem_text(item.find("pubDate"))
        rank_el  = item.find("rank")
        rank     = int(_elem_text(rank_el)) if rank_el is not None and _elem_text(rank_el).isdigit() else 99
        insight  = _elem_text(item.find("insight"))

        if not title:
            continue

        summary = _extract_key_point(insight) or desc[:200]

        results.append({
            "title":     title,
            "summary":   summary[:200],
            "link":      link,
            "source":    "NS3.ai",
            "pub_time":  pub_date,
            "rank":      rank,
            "level":     2,         # Top News 全为 L1/L2
            "news_type": "important",
            "insight":   insight,
            "category":  _classify_news_by_keyword(title, summary),
        })

    results.sort(key=lambda x: x["rank"])
    logger.debug(f"NS3 Top News 获取 {len(results)} 条")
    return results


# ═══════════════════════════════════════════════════════════
# Feed 3: Daily Briefing — 24h 综述简报（最轻量，~2000 token）
# ═══════════════════════════════════════════════════════════

def fetch_daily_briefing(lang: str = NS3_LANG) -> Optional[str]:
    """
    获取 NS3 每日综述简报（Feed 3）
    返回 Markdown 格式全文，含 Top Stories / Market Trends / Regulation 等章节
    """
    url = f"{NS3_BASE}/today-summary?lang={lang}"
    logger.debug(f"NS3 Daily Briefing: {url}")
    items_raw = _fetch_xml(url, tag="item")
    if not items_raw:
        return None

    for item in items_raw:
        desc = _elem_text(item.find("description"))
        if desc:
            return _clean_html(desc)
    return None


# ═══════════════════════════════════════════════════════════
# Feed 4: Breaking News — 突发头条（Bloomberg/Reuters 速报）
# ═══════════════════════════════════════════════════════════

def fetch_breaking_news(lang: str = NS3_LANG, limit: int = 20) -> list[dict]:
    """
    获取 NS3 突发新闻速报（Feed 4，Pipeline B）
    来源：Bloomberg Terminal / Reuters，1-2 句话的即时头条
    """
    url = f"{NS3_BASE}/news-flash?lang={lang}&limit={limit}"
    logger.debug(f"NS3 Breaking News: {url}")
    items_raw = _fetch_xml(url, tag="item")
    if not items_raw:
        return []

    results = []
    for item in items_raw:
        title    = _clean_html(_elem_text(item.find("title")))
        pub_date = _elem_text(item.find("pubDate"))
        if not title:
            continue
        if not _is_recent(pub_date, max_hours=12):
            continue

        is_breaking = title.upper().startswith("[BREAKING]")
        results.append({
            "title":      title,
            "summary":    "",
            "link":       "",
            "source":     "NS3.ai (Bloomberg/Reuters)",
            "pub_time":   pub_date,
            "level":      1 if is_breaking else 2,
            "news_type":  "breaking" if is_breaking else "important",
            "category":   _classify_news_by_keyword(title, ""),
        })

    logger.debug(f"NS3 Breaking News 获取 {len(results)} 条")
    return results


# ═══════════════════════════════════════════════════════════
# 主入口 — 整合四个 Feed，按分类输出
# ═══════════════════════════════════════════════════════════

def fetch_all_news() -> dict[str, list[dict]]:
    """
    整合 NS3 四个 Feed，按分类（宏观/监管/市场/链上）聚合并输出

    策略：
    1. 优先用 Top News（L1/L2 最重要新闻），确保质量
    2. 用 News RSS（excludeLevels=4）补充数量
    3. Breaking News 追加到对应分类
    每类最多 MAX_NEWS_PER_CATEGORY 条
    """
    logger.info("抓取新闻...")
    all_items: list[dict] = []

    # ── Step A：Top News（L1/L2，权重最高）──
    try:
        top_items = fetch_top_news()
        all_items.extend(top_items)
        logger.debug(f"  Top News: {len(top_items)} 条")
    except Exception as e:
        logger.warning(f"Top News 获取失败: {e}")
    time.sleep(0.5)

    # ── Step B：News RSS（L1-L3，排除 L4 常规信息）──
    try:
        rss_items = fetch_news_rss(
            lang=NS3_LANG,
            limit=40,
            exclude_levels="4",
        )
        all_items.extend(rss_items)
        logger.debug(f"  News RSS: {len(rss_items)} 条")
    except Exception as e:
        logger.warning(f"News RSS 获取失败: {e}")
    time.sleep(0.5)

    # ── Step C：Breaking News（过去 12h 突发）──
    try:
        flash_items = fetch_breaking_news(limit=15)
        all_items.extend(flash_items)
        logger.debug(f"  Breaking News: {len(flash_items)} 条")
    except Exception as e:
        logger.warning(f"Breaking News 获取失败: {e}")

    # ── 去重 ──
    all_items = _deduplicate(all_items)

    # ── 按分类分配（L1/L2 优先）──
    all_items.sort(key=lambda x: (x.get("level", 3), x.get("rank", 99)))

    result: dict[str, list[dict]] = {"宏观": [], "监管": [], "市场": [], "链上": []}
    for item in all_items:
        cat = item.get("category", "市场")
        if cat not in result:
            cat = _classify_news_by_keyword(item["title"], item.get("summary", ""))
        if len(result.get(cat, [])) < MAX_NEWS_PER_CATEGORY:
            result.setdefault(cat, []).append(item)

    total = sum(len(v) for v in result.values())
    logger.info(f"新闻获取完成，共 {total} 条")
    return result


def format_news_section(news: dict[str, list[dict]]) -> str:
    """
    生成新闻速递 Markdown 文本
    """
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
        lines.append(f"\n{icon}")
        for item in items:
            title  = item["title"]
            source = item.get("source", "NS3.ai")
            lines.append(f"· {title}（{source}）")

    return "\n".join(lines) if lines else "· 暂无最新要闻"
