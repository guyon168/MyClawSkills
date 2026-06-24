#!/usr/bin/env python3
"""Export real weekly crypto market data for WorkBuddy report generation.

This script intentionally does not call any external LLM provider. It collects
real data step by step, tolerates partial source failures, and always writes a
JSON payload for the current WorkBuddy conversation model to analyze.
"""

from __future__ import annotations

import json
import signal
import sys
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

SOCIAL_TIMEOUT_SECONDS = 30
STEP_TIMEOUT_SECONDS = 45
OUTPUT_JSON_FILENAME = "weekly_data_current.json"


class StepTimeoutError(TimeoutError):
    """Raised when a collector step exceeds its allowed runtime."""


@contextmanager
def time_limit(seconds: int, step_name: str):
    """Limit a synchronous collector step using SIGALRM on Unix."""

    def handle_timeout(_signum: int, _frame: Any) -> None:
        raise StepTimeoutError(f"{step_name} timed out after {seconds}s")

    previous_handler = signal.signal(signal.SIGALRM, handle_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def find_project_root() -> Path:
    """Return the nearest parent project root containing the crypto_bot package."""
    current_path = Path(__file__).resolve()
    candidate_paths = [Path.cwd().resolve(), current_path.parent, *current_path.parents]
    checked_paths: set[Path] = set()

    for candidate_path in candidate_paths:
        for parent_path in [candidate_path, *candidate_path.parents]:
            if parent_path in checked_paths:
                continue
            checked_paths.add(parent_path)
            if (parent_path / "crypto_bot" / "main.py").exists():
                return parent_path

    raise FileNotFoundError(
        "Unable to locate project root containing crypto_bot/main.py. "
        "Run this script from the crypto weekly report project root or install "
        "the skill beneath that project."
    )


def make_json_safe(value: Any) -> Any:
    """Convert values returned by collectors into JSON-serializable objects."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]
    if isinstance(value, set):
        return sorted(make_json_safe(item) for item in value)
    return value


def run_step(
    name: str,
    data: dict[str, Any],
    errors: dict[str, Any],
    default_value: Any,
    collector: Callable[[], Any],
) -> Any:
    """Run one collector with isolation and store an error on failure."""
    print(f"[EXPORT] Step: {name}", flush=True)
    try:
        with time_limit(STEP_TIMEOUT_SECONDS, name):
            value = collector()
        if value is None:
            raise ValueError(f"{name} returned None")
        print(f"[EXPORT] Step OK: {name}", flush=True)
        return value
    except Exception as exc:  # noqa: BLE001 - export must tolerate source failures.
        message = f"{type(exc).__name__}: {exc}"
        errors[name] = message
        print(f"[EXPORT] Step FAILED: {name}: {message}", flush=True)
        return default_value


def fetch_social_with_timeout(errors: dict[str, Any]) -> dict[str, Any]:
    """Fetch social data with a hard timeout and safe fallback."""
    result: dict[str, Any] = {"tweets": [], "total": 0, "kols_count": 0}
    error_holder: dict[str, str] = {}
    completed = threading.Event()

    def do_fetch() -> None:
        try:
            from crypto_bot.fetchers.social import fetch_crypto_twitter_sentiment

            fetched = fetch_crypto_twitter_sentiment()
            if isinstance(fetched, dict):
                result.update(fetched)
            else:
                error_holder["social"] = f"Unexpected result type: {type(fetched).__name__}"
        except Exception as exc:  # noqa: BLE001 - social must never block export.
            error_holder["social"] = f"{type(exc).__name__}: {exc}"
        finally:
            completed.set()

    thread = threading.Thread(target=do_fetch, daemon=True)
    thread.start()
    completed.wait(timeout=SOCIAL_TIMEOUT_SECONDS)

    if not completed.is_set():
        message = f"Timeout after {SOCIAL_TIMEOUT_SECONDS}s"
        errors["social"] = message
        return {"tweets": [], "total": 0, "kols_count": 0, "error": message}

    if error_holder:
        message = error_holder["social"]
        errors["social"] = message
        return {"tweets": [], "total": 0, "kols_count": 0, "error": message}

    result.setdefault("tweets", [])
    result.setdefault("total", len(result.get("tweets", [])))
    result.setdefault("kols_count", 0)
    return result


def collect_data_resilient(no_cache: bool = True) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Collect data source by source and continue after partial failures."""
    from crypto_bot.main import clear_cache

    if no_cache:
        clear_cache()

    data: dict[str, Any] = {}
    errors: dict[str, Any] = {}
    source_status: dict[str, Any] = {}

    def collect_price() -> dict[str, Any]:
        from crypto_bot.fetchers.price import fetch_price_all

        return fetch_price_all()

    data["price"] = run_step("price", data, errors, {}, collect_price)

    def collect_tech() -> dict[str, Any]:
        from crypto_bot.fetchers.price import fetch_technical_indicators

        return fetch_technical_indicators("BTCUSDT")

    data["tech"] = run_step("tech", data, errors, {}, collect_tech)

    def collect_weekly_perf() -> dict[str, Any]:
        from crypto_bot.fetchers.price import fetch_weekly_performance

        return fetch_weekly_performance()

    data["weekly_perf"] = run_step("weekly_perf", data, errors, {}, collect_weekly_perf)

    def collect_etf() -> dict[str, Any]:
        from crypto_bot.fetchers.etf import fetch_etf_flows

        return {"BTC": fetch_etf_flows("BTC"), "ETH": fetch_etf_flows("ETH")}

    data["etf"] = run_step("etf", data, errors, {"BTC": {}, "ETH": {}}, collect_etf)

    def collect_sentiment() -> dict[str, Any]:
        from crypto_bot.fetchers.sentiment import fetch_fear_greed

        return fetch_fear_greed()

    data["sentiment"] = run_step("sentiment", data, errors, {}, collect_sentiment)

    def collect_news() -> list[Any]:
        from crypto_bot.fetchers.news import fetch_weekly_news, get_news_source_status

        fetched_news = fetch_weekly_news(max_total=50)
        source_status["news"] = get_news_source_status()
        return fetched_news

    data["news"] = run_step("news", data, errors, [], collect_news)
    source_status.setdefault("news", _safe_get_news_source_status())

    def collect_calendar() -> list[Any]:
        from crypto_bot.fetchers.macro import fetch_next_week_calendar, get_macro_errors, get_macro_source_status

        fetched_calendar = fetch_next_week_calendar()
        source_status["macro"] = get_macro_source_status()
        macro_errors = get_macro_errors()
        if macro_errors:
            errors["macro_sources"] = macro_errors
        return fetched_calendar

    data["calendar"] = run_step("calendar", data, errors, [], collect_calendar)
    source_status.setdefault("macro", _safe_get_macro_source_status())
    macro_errors = _safe_get_macro_errors()
    if macro_errors and "macro_sources" not in errors:
        errors["macro_sources"] = macro_errors

    print("[EXPORT] Step: social", flush=True)
    data["social"] = fetch_social_with_timeout(errors)
    print(f"[EXPORT] Step finished: social, total={data['social'].get('total', 0)}", flush=True)

    return data, errors, source_status


def _safe_get_news_source_status() -> dict[str, Any]:
    """Safely read news source status after a failed news step."""
    try:
        from crypto_bot.fetchers.news import get_news_source_status

        return get_news_source_status()
    except Exception:  # noqa: BLE001 - status collection must not block export.
        return {}


def _safe_get_macro_source_status() -> dict[str, Any]:
    """Safely read macro source status after a failed calendar step."""
    try:
        from crypto_bot.fetchers.macro import get_macro_source_status

        return get_macro_source_status()
    except Exception:  # noqa: BLE001 - status collection must not block export.
        return {}


def _safe_get_macro_errors() -> list[str]:
    """Safely read macro source errors after a failed calendar step."""
    try:
        from crypto_bot.fetchers.macro import get_macro_errors

        return get_macro_errors()
    except Exception:  # noqa: BLE001 - status collection must not block export.
        return []


def build_payload(
    raw_data: dict[str, Any],
    meta: dict[str, Any],
    errors: dict[str, Any],
    source_status: dict[str, Any],
) -> dict[str, Any]:
    """Build the canonical JSON payload consumed by WorkBuddy."""
    payload: dict[str, Any] = {
        "meta": make_json_safe(meta),
        "price": make_json_safe(raw_data.get("price", {})),
        "tech": make_json_safe(raw_data.get("tech", {})),
        "weekly_perf": make_json_safe(raw_data.get("weekly_perf", {})),
        "etf": make_json_safe(raw_data.get("etf", {})),
        "sentiment": make_json_safe(raw_data.get("sentiment", {})),
        "news": make_json_safe(raw_data.get("news", [])),
        "calendar": make_json_safe(raw_data.get("calendar", [])),
        "social": make_json_safe(raw_data.get("social", {"tweets": [], "total": 0, "kols_count": 0})),
        "errors": make_json_safe(errors),
        "source_status": make_json_safe(source_status),
    }
    payload["export_info"] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "resilient per-source real collectors",
        "llm_called": False,
        "notes": (
            "Raw real fetched data only. Calendar never uses generated fallback rules; "
            "source_status records every news and macro source outcome."
        ),
    }
    return payload


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a concise machine-readable summary for stdout."""
    price = payload.get("price", {})
    tech = payload.get("tech", {})
    etf = payload.get("etf", {})
    sentiment = payload.get("sentiment", {})
    social = payload.get("social", {})
    source_status = payload.get("source_status", {})
    return {
        "btc_price": price.get("BTC", {}).get("price"),
        "eth_price": price.get("ETH", {}).get("price"),
        "bnb_price": price.get("BNB", {}).get("price"),
        "btc_ema50": tech.get("ema50"),
        "btc_ema200": tech.get("ema200"),
        "btc_etf_week_net_millions": etf.get("BTC", {}).get("week_net"),
        "eth_etf_week_net_millions": etf.get("ETH", {}).get("week_net"),
        "fear_greed": sentiment.get("current", {}),
        "news_count": len(payload.get("news", [])),
        "calendar_count": len(payload.get("calendar", [])),
        "social_tweet_count": social.get("total", 0) if isinstance(social, dict) else 0,
        "news_source_status": source_status.get("news", {}),
        "macro_source_status": source_status.get("macro", {}),
        "errors": payload.get("errors", {}),
    }


def main() -> int:
    """Collect real data and export a current weekly data JSON file."""
    project_root = find_project_root()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    output_dir = project_root / "crypto_bot" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_JSON_FILENAME
    raw_data: dict[str, Any] = {}
    errors: dict[str, Any] = {}
    source_status: dict[str, Any] = {"news": {}, "macro": {}}
    meta: dict[str, Any] = {}
    exit_code = 0

    try:
        from crypto_bot.generators.report import build_meta

        print(f"[EXPORT] Project root: {project_root}", flush=True)
        print("[EXPORT] Collecting real weekly data without external LLM...", flush=True)
        raw_data, errors, source_status = collect_data_resilient(no_cache=True)
        meta = run_step("meta", raw_data, errors, {}, build_meta)
    except Exception as exc:  # noqa: BLE001 - must still write JSON.
        exit_code = 1
        errors["fatal"] = f"{type(exc).__name__}: {exc}"
        print(f"[EXPORT] Fatal but writing JSON: {errors['fatal']}", flush=True)
    finally:
        raw_data.setdefault("price", {})
        raw_data.setdefault("tech", {})
        raw_data.setdefault("weekly_perf", {})
        raw_data.setdefault("etf", {"BTC": {}, "ETH": {}})
        raw_data.setdefault("sentiment", {})
        raw_data.setdefault("news", [])
        raw_data.setdefault("calendar", [])
        raw_data.setdefault("social", {"tweets": [], "total": 0, "kols_count": 0})
        source_status.setdefault("news", _safe_get_news_source_status())
        source_status.setdefault("macro", _safe_get_macro_source_status())
        payload = build_payload(raw_data=raw_data, meta=meta, errors=errors, source_status=source_status)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = summarize_payload(payload)
        print(f"[EXPORT] JSON saved: {output_path}", flush=True)
        print("[EXPORT] Summary:", flush=True)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
