"""
Twitter/X 热点模块 - FxTwitter + Nitter 双源方案

数据流：
  Nitter RSS（稳定） → 提取推文链接 + tweet ID
                ↓
  FxTwitter API（https://api.fxtwitter.com/{user}/status/{id}）
              → 获取完整推文内容、互动数据

Nitter 为主源（无需 key，公开可用），FxTwitter 为增强层（获取完整文本和互动统计）。
"""
import sys
import os
import time
import logging
import re
import requests
import feedparser
from typing import Optional

# ── 代理配置 ──────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from config import PROXIES, USE_PROXY
except ImportError:
    PROXIES = None
    USE_PROXY = False

logger = logging.getLogger(__name__)

# ── Nitter 实例（多备选，直连优先，代理兜底）─────────────
# 优先用前面几个，nitter.net 作为兜底
_NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.moomoo.me",
    "https://nitter.net",
]

# ── FxTwitter API ─────────────────────────────────────────
_FXTWITTER_BASE = "https://api.fxtwitter.com"
_FXTWITTER_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}

# ── KOL 列表（当代 Crypto 核心风向标）────────────────────
# lookonchain  链上巨鲸与Smart Money核心
# ArthurHayes  衍生品与宏观大格局
# cobie        行业思想领袖，情绪催化剂
# VitalikButerin  以太坊叙事与生态技术风向标
# blknoiz06    阿尔法山寨与Meme市场热点（Ansem）
# zachxbt      安全、雷区、黑客与突发情报
# HsakaTrades  顶级敏锐度日内衍生品大作手
# rektcapital  趋势与结构分析（保留）
# PeterLBrandt  经典波段大师（保留）
TWITTER_KOLS = [
    "lookonchain",
    "ai_9684xtpa",
    "cz_binance",
    "VitalikButerin",
    "EmberCN",
    "zachxbt"
]

# ── 过滤关键词（当代 Web3 + 链上 + 叙事全覆盖）───────────
# 链上动向 / 安全突发 / 交易情绪 / 政策与叙事
_CRYPTO_KEYWORDS = [
    # 主流币种
    "btc", "bitcoin", "eth", "ethereum", "sol", "solana", "crypto",
    # 链上巨鲸动向（lookonchain 系核心）
    "whale", "whales", "deposited", "withdrew", "bought", "sold",
    "liquidated", "transfer", "wallet", "exchange", " inflows", "outflows",
    # 安全与突发（zachxbt 系）
    "hack", "exploit", "scam", "rug", "phishing", "breach", "stolen",
    "drained", "vulnerability", "alert",
    # 交易情绪
    "bullish", "bearish", "long", "short", "fomo", "dump", "pump",
    "breakout", "breakdown", "support", "resistance", "target",
    # 市场与策略
    "market", "price", "trend", "analysis", "signal", "trade", "trading",
    "strategy", "position", "entry", "exit", "stop loss", "tp",
    # 叙事与事件
    "meme", "airdrop", "listing", "sec", "fed", "rate", "etf",
    "adoption", "regulation", "macro", "inflation",
]

# ── 限制参数 ─────────────────────────────────────────────
MAX_TWEETS_PER_KOL = 2
MAX_TOTAL_TWEETS = 6


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def _clean_tweet(text: str) -> str:
    """清理推文文本"""
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'<[^>]+>', '', text)
    # 截断过长文本（给翻译留足上下文）
    if len(text) > 400:
        text = text[:397] + "..."
    return text


# ── 强过滤黑名单（非加密内容，排除个人生活分享）─────────
_NON_CRYPTO_BLACKLIST = [
    # 社媒/娱乐内容（非交易讨论）
    "tiktok", "instagram", "youtube short", "youtube video",
    "anime", "manga", "chess", "pizza", "coffee",
    "dinner", "lunch", "breakfast",
    "my cat", "my dog", "my kids", "my wife", "my husband",
    "happy birthday", "merry christmas",
    # Polymarket 非加密/非宏观话题（体育/娱乐预测直接过滤）
    "football", "basketball", "soccer", "game ", "game 1",
    "nba", "nfl", "world cup", "olympics",
    "president", "election", "election odds",
    # 内容吐槽类（KOL 个人吐槽，非 Alpha）
    "who is this for", "target audience", "why do they",
]

# ── 高权重关键词（出现这些直接提升通过率）───────────────
_HIGH_VALUE_KW = [
    # 具体数字/金额类（Alpha 推文核心）
    "$", "000", "million", "billion", "million", "bought", "sold",
    "deposited", "withdrew", "wallet", "address", "0x",
    # 明确交易/盈亏
    "long", "short", "liquidated", "leverage", "profit", "loss",
    "entry", "exit", "target", "stop", "pnl",
]


def _is_crypto_related(text: str) -> bool:
    """
    增强版过滤：至少命中 2 个加密关键词 OR 高权重关键词，
    同时不在黑名单中。
    """
    text_lower = text.lower()

    # 黑名单排除（个人生活分享）
    if any(bw in text_lower for bw in _NON_CRYPTO_BLACKLIST):
        return False

    # 高权重关键词命中：直接通过（Alpha 内容）
    high_value_hits = sum(1 for kw in _HIGH_VALUE_KW if kw in text_lower)
    if high_value_hits >= 1:
        return True

    # 普通关键词命中计数
    keyword_hits = sum(1 for kw in _CRYPTO_KEYWORDS if kw in text_lower)
    return keyword_hits >= 2


def _extract_tweet_id_from_link(link: str) -> Optional[str]:
    """从 Nitter 链接中提取 tweet ID"""
    # 格式: https://nitter.net/PeterLBrandt/status/2056919781928996952#m
    m = re.search(r'/status/(\d+)', link)
    return m.group(1) if m else None


# ═══════════════════════════════════════════════════════════
# Nitter RSS 抓取（稳定主源）
# ═══════════════════════════════════════════════════════════

def _fetch_nitter_rss(username: str) -> list[dict]:
    """
    从 Nitter RSS 获取用户最新推文列表。
    返回: [{"title": ..., "link": ..., "pub_date": ...}, ...]
    """
    for instance in _NITTER_INSTANCES:
        url = f"{instance}/{username}/rss"
        feed = None

        # 方式 1: feedparser 直连（绕过代理不稳定问题）
        try:
            import socket
            old = socket.getdefaulttimeout()
            socket.setdefaulttimeout(12)
            try:
                feed = feedparser.parse(url)
            finally:
                socket.setdefaulttimeout(old)
        except Exception as e:
            logger.debug(f"Nitter 直连失败 {instance}/{username}: {e}")

        # 方式 2: requests via 代理兜底
        if feed is None or (feed.bozo and not feed.entries):
            if USE_PROXY and PROXIES:
                try:
                    r = requests.get(
                        url,
                        timeout=8,
                        proxies=PROXIES,
                        headers={"User-Agent": "Mozilla/5.0"},
                    )
                    r.raise_for_status()
                    feed = feedparser.parse(r.text)
                except Exception as e:
                    logger.debug(f"Nitter 代理请求失败 {instance}/{username}: {e}")

        if feed is None or (feed.bozo and not feed.entries):
            continue  # 尝试下一个实例

        tweets = []
        for entry in feed.entries[:6]:
            title   = _clean_tweet(entry.get("title", ""))
            link    = entry.get("link", "")
            pub_date = entry.get("published", "")
            if not title or not _is_crypto_related(title):
                continue
            tweets.append({
                "username": f"@{username}",
                "text":     title,
                "link":     link,
                "pub_date": pub_date,
            })
            if len(tweets) >= MAX_TWEETS_PER_KOL:
                break
        return tweets

    return []


# ═══════════════════════════════════════════════════════════
# FxTwitter API（增强层，获取完整内容和互动统计）
# ═══════════════════════════════════════════════════════════

def _fetch_fxtwitter(username: str, tweet_id: str) -> Optional[dict]:
    """
    通过 FxTwitter API 获取单条推文完整数据。
    返回: {"text": ..., "likes": ..., "retweets": ..., ...} 或 None
    """
    url = f"{_FXTWITTER_BASE}/{username}/status/{tweet_id}"
    try:
        resp = requests.get(
            url,
            proxies=PROXIES,
            headers=_FXTWITTER_HEADERS,
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        tweet = data.get("tweet", {})
        return {
            "text":      tweet.get("text", ""),
            "likes":     tweet.get("likes", 0) or 0,
            "retweets":  tweet.get("retweets", 0) or 0,
            "replies":   tweet.get("replies", 0) or 0,
        }
    except Exception as e:
        logger.debug(f"FxTwitter 获取失败 {username}/{tweet_id}: {e}")
        return None


# ═══════════════════════════════════════════════════════════
# 翻译（MyMemory 免费 API）
# ═══════════════════════════════════════════════════════════

def _translate_en_to_zh(text: str) -> str:
    """使用 MyMemory 免费 API 将英文翻译为中文"""
    if not text or not text.strip():
        return text

    text = text.strip()
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if chinese_chars > len(text) * 0.3:
        return text

    MYMEMORY_URL = "https://api.mymemory.translated.net/get"
    MAX_CHUNK = 450

    def _translate_chunk(chunk: str) -> str:
        try:
            resp = requests.get(
                MYMEMORY_URL,
                params={"q": chunk, "langpair": "en|zh-CN", "de": "noreply@ns3.ai"},
                proxies=PROXIES,
                timeout=8,
                headers={"User-Agent": "crypto-daily-bot/1.0"},
            )
            if resp.status_code == 200:
                result = resp.json()
                translated = result.get("responseData", {}).get("translatedText", "")
                if translated and translated.strip():
                    return translated.strip()
        except Exception:
            pass
        return chunk

    if len(text) <= MAX_CHUNK:
        return _translate_chunk(text)

    # 按句子切分（防 API 截断）
    sentences = re.split(r'(?<=[.!?\n])\s+', text)
    chunks, current = [], ""
    for sentence in sentences:
        if len(current) + len(sentence) <= MAX_CHUNK:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
            while len(sentence) > MAX_CHUNK:
                chunks.append(sentence[:MAX_CHUNK])
                sentence = sentence[MAX_CHUNK:]
            current = sentence
    if current:
        chunks.append(current)

    results = []
    for i, chunk in enumerate(chunks):
        results.append(_translate_chunk(chunk))
        if i < len(chunks) - 1:
            time.sleep(0.3)

    return " ".join(results)


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def fetch_twitter_hotspots() -> list[dict]:
    """
    抓取 KOL 热点推文（FxTwitter + Nitter 双源）。
    流程：
      1. Nitter RSS 获取推文链接列表（稳定）
      2. 从链接提取 tweet ID
      3. FxTwitter API 获取完整推文内容（增强）
      4. 英文推文翻译为中文
    """
    logger.info("抓取 Twitter/X 热点...")
    all_tweets: list[dict] = []

    for username in TWITTER_KOLS:
        if len(all_tweets) >= MAX_TOTAL_TWEETS:
            break

        # ── Step 1: Nitter RSS 获取推文列表 ──
        nitter_tweets = _fetch_nitter_rss(username)
        if not nitter_tweets:
            logger.debug(f"Nitter RSS 获取 {username} 失败")
            time.sleep(0.5)
            continue

        # ── Step 2: FxTwitter 逐条获取完整内容 ──
        for item in nitter_tweets:
            if len(all_tweets) >= MAX_TOTAL_TWEETS:
                break

            tweet_id = _extract_tweet_id_from_link(item["link"])
            if tweet_id:
                fx_data = _fetch_fxtwitter(username, tweet_id)
                if fx_data:
                    text = fx_data["text"]
                else:
                    text = item["text"]  # Nitter 原文兜底
            else:
                text = item["text"]

            # 翻译（英文才翻）
            if not any('\u4e00' <= c <= '\u9fff' for c in text):
                text = _translate_en_to_zh(text)

            all_tweets.append({
                "username":  item["username"],
                "text":      text,
                "link":      item["link"],
            })

        time.sleep(0.3)

    logger.info(f"  共 {len(all_tweets)} 条热点")
    return all_tweets[:MAX_TOTAL_TWEETS]


def format_twitter_section(tweets: list[dict]) -> str:
    """生成 Twitter 热点 Markdown 文本"""
    if not tweets:
        return "· 暂无 Twitter 热点数据（Nitter 实例均不可达）"

    lines = []
    for t in tweets:
        lines.append(f"· {t['username']}：{t['text']}")

    return "\n".join(lines)
