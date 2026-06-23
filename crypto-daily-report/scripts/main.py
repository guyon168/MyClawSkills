"""
AI 加密日报 - 主入口
用法:
  python main.py           # 生成今日报告并输出到 reports/
  python main.py --print   # 同时打印到控制台
  python main.py --test    # 仅测试数据获取，不保存文件
"""
import argparse
import logging
import sys
import os
import time
from datetime import datetime, timezone, timedelta

# 确保项目目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    COINS,
    REPORTS_DIR,
    LOGS_DIR,
    PROXIES,
    PUSH_ENABLED,
    PUSH_PROVIDER,
    WECHAT_WEBHOOK,
    MATTERMOST_WEBHOOK,
    MATTERMOST_USERNAME,
)
from modules.crypto_data import analyze_coin
from modules.macro_data import fetch_all_macro
from modules.news_fetcher import fetch_all_news
from modules.twitter_hotspot import fetch_twitter_hotspots
from modules.risk_analyzer import analyze_risks
from modules.report_renderer import render_report, save_report
from modules.wechat_pusher import push_to_wechat
from modules.mattermost_pusher import push_to_mattermost

TZ_CN = timezone(timedelta(hours=8))


# ─────────────────────────────────────────────────────
# 日志配置
# ─────────────────────────────────────────────────────

def setup_logging(log_dir: str, verbose: bool = False):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, datetime.now(TZ_CN).strftime("%Y-%m-%d") + ".log")

    level = logging.DEBUG if verbose else logging.INFO
    handlers = [
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


# ─────────────────────────────────────────────────────
# 推送路由
# ─────────────────────────────────────────────────────

def push_report(report_text: str) -> bool:
    logger = logging.getLogger("main")
    provider = (PUSH_PROVIDER or "").lower().strip()

    if provider == "wechat":
        if not WECHAT_WEBHOOK:
            logger.warning("已选择企业微信推送，但 WECHAT_WEBHOOK 未配置")
            return False
        logger.info("Step 6/6: 推送到企业微信...")
        return push_to_wechat(WECHAT_WEBHOOK, report_text, PROXIES)

    if provider == "mattermost":
        if not MATTERMOST_WEBHOOK:
            logger.warning("已选择 Mattermost 推送，但 MATTERMOST_WEBHOOK 未配置")
            return False
        logger.info("Step 6/6: 推送到 Mattermost...")
        return push_to_mattermost(
            MATTERMOST_WEBHOOK,
            report_text,
            PROXIES,
            username=MATTERMOST_USERNAME,
        )

    logger.warning(f"未知 PUSH_PROVIDER: {PUSH_PROVIDER}，可选值为 wechat / mattermost")
    return False


# ─────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────

def run(print_report: bool = False, test_mode: bool = False):
    logger = logging.getLogger("main")
    start_time = time.time()

    now_cn = datetime.now(TZ_CN)
    logger.info(f"═══ AI 加密日报 生成开始 {now_cn.strftime('%Y-%m-%d %H:%M')} ═══")

    # ──────────────────────────────
    # Step 1: 加密货币技术分析
    # ──────────────────────────────
    logger.info("Step 1/5: 获取加密货币数据与技术分析...")
    coins_data = []
    for coin in COINS:
        data = analyze_coin(coin)
        coins_data.append(data)
        if data:
            ticker = data["ticker"]
            ta     = data["ta"]
            logger.info(
                f"  {coin['symbol']}: ${ticker['price']:,.2f} "
                f"({'+' if ticker['change_pct']>=0 else ''}{ticker['change_pct']:.2f}%) "
                f"| 趋势: {ta['trend_bias']} | RSI: {ta['rsi']:.1f}"
            )
        else:
            logger.warning(f"  {coin['symbol']}: 数据获取失败")
        time.sleep(0.5)

    # ──────────────────────────────
    # Step 2: 宏观数据
    # ──────────────────────────────
    logger.info("Step 2/5: 获取宏观数据...")
    macro = fetch_all_macro()

    gold = macro.get("gold")
    oil  = macro.get("oil")
    dxy  = macro.get("dxy")
    fg   = macro.get("fear_greed")
    cg   = macro.get("crypto_global")

    if gold: logger.info(f"  黄金: ${gold['price']:,.0f} ({_fmt_pct(gold['change_pct'])})")
    if oil:  logger.info(f"  原油: ${oil['price']:.2f} ({_fmt_pct(oil['change_pct'])})")
    if dxy:  logger.info(f"  DXY: {dxy['price']:.2f}")
    if fg:   logger.info(f"  恐贪指数: {fg['value']} {fg['label']}")
    if cg:   logger.info(f"  BTC主导率: {cg['btc_dominance']}% | 总市值: ${cg['total_mcap']/1e12:.2f}T")

    # ──────────────────────────────
    # Step 3: 新闻聚合
    # ──────────────────────────────
    logger.info("Step 3/5: 抓取新闻...")
    news = fetch_all_news()
    for cat, items in news.items():
        logger.info(f"  {cat}: {len(items)} 条")

    # ──────────────────────────────
    # Step 4: Twitter 热点
    # ──────────────────────────────
    logger.info("Step 4/5: 获取 Twitter 热点...")
    tweets = fetch_twitter_hotspots()
    if not tweets:
        logger.info("  Twitter 抓取失败，Twitter 版块将显示'暂无数据'")
    logger.info(f"  共 {len(tweets)} 条热点")

    # ──────────────────────────────
    # Step 5: 风险分析 + 报告生成
    # ──────────────────────────────
    logger.info("Step 5/5: 分析风险并生成报告...")
    risk_analysis = analyze_risks(news, macro)
    logger.info(f"  风险等级: {risk_analysis['risk_level']} | 检测到 {len(risk_analysis['risks'])} 个风险点")
    logger.info(f"  川普信号: {risk_analysis['trump_signal']['label']}")

    # ──────────────────────────────
    # 渲染报告
    # ──────────────────────────────
    report_text = render_report(
        coins_data    = coins_data,
        macro         = macro,
        news          = news,
        tweets        = tweets,
        risk_analysis = risk_analysis,
    )

    if print_report:
        # Windows 控制台编码兼容
        import sys, io
        try:
            out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            out.write("\n" + "═" * 60 + "\n")
            out.write(report_text)
            out.write("\n" + "═" * 60 + "\n")
            out.flush()
        except Exception:
            # 降级：去掉 emoji 后打印
            safe = report_text.encode("gbk", errors="replace").decode("gbk")
            print("\n" + "=" * 60)
            print(safe)
            print("=" * 60 + "\n")

    if not test_mode:
        filepath = save_report(report_text, REPORTS_DIR)
        logger.info(f"报告已保存: {filepath}")

        # ──────────────────────────────
        # Step 6: 按配置推送 Webhook
        # ──────────────────────────────
        if PUSH_ENABLED:
            success = push_report(report_text)
            if success:
                logger.info("Webhook 推送成功")
            else:
                logger.warning("Webhook 推送失败，请检查配置")
    else:
        logger.info("[TEST MODE] 未保存文件")

    elapsed = time.time() - start_time
    logger.info(f"═══ 完成！耗时 {elapsed:.1f}s ═══")

    return report_text


def _fmt_pct(pct: float) -> str:
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


# ─────────────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI 加密日报生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py              # 生成报告并保存
  python main.py --print      # 生成并打印到控制台
  python main.py --test       # 测试模式（不保存文件）
  python main.py --verbose    # 详细日志
        """,
    )
    parser.add_argument("--print",   action="store_true", help="打印报告到控制台")
    parser.add_argument("--test",    action="store_true", help="测试模式，不保存文件")
    parser.add_argument("--verbose", action="store_true", help="详细日志")
    args = parser.parse_args()

    setup_logging(LOGS_DIR, verbose=args.verbose)

    try:
        run(
            print_report = args.print or args.test,
            test_mode    = args.test,
        )
    except KeyboardInterrupt:
        print("\n中断")
        sys.exit(0)
    except Exception as e:
        logging.getLogger("main").exception(f"运行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
