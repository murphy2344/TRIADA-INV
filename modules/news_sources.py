"""Resilient multi-source RSS ingestion for global financial news.

Feeds are fetched concurrently with bounded workers. A failing publisher is
cooled down independently, so one 429/timeout never blocks healthy sources.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
import feedparser
import hashlib
import logging
import threading
import time
import requests

from config.config import RSS_FEEDS

logger = logging.getLogger(__name__)

RSS_TIMEOUT_SECONDS = 8
RSS_FAILURE_COOLDOWN_SECONDS = 15 * 60
RSS_MAX_COOLDOWN_SECONDS = 6 * 60 * 60
RSS_MAX_WORKERS = 6
RSS_USER_AGENT = "TRIADA-INV/1.0 (+global financial news reader)"
_feed_retry_after: dict[str, float] = {}
_feed_failures: dict[str, int] = {}
_feed_failure_logged: set[str] = set()
_host_retry_after: dict[str, float] = {}
_feed_cache_headers: dict[str, dict[str, str]] = {}
_state_lock = threading.Lock()


def _make_id(url: str, title: str) -> str:
    return hashlib.sha256(f"{url}\n{title}".encode("utf-8")).hexdigest()


def _extract_rss_image(entry) -> str | None:
    for group in (entry.get("media_content", []), entry.get("media_thumbnail", [])):
        for media in group:
            url = media.get("url", "")
            if url:
                return url
    for enclosure in entry.get("enclosures", []):
        url = enclosure.get("url", "")
        if url and enclosure.get("type", "").startswith("image/"):
            return url
    for link in entry.get("links", []):
        url = link.get("href", "")
        if url and link.get("type", "").startswith("image/"):
            return url
    return None


def _published_at(entry) -> str:
    value = entry.get("published") or entry.get("updated") or ""
    if value:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
    return ""


def _fetch_one(source: str, feed_url: str, limit_per_feed: int) -> list[dict]:
    now = time.monotonic()
    host = urlparse(feed_url).netloc.lower()
    with _state_lock:
        if _feed_retry_after.get(source, 0) > now or _host_retry_after.get(host, 0) > now:
            return []
        headers = {"User-Agent": RSS_USER_AGENT, **_feed_cache_headers.get(source, {})}

    try:
        response = requests.get(feed_url, timeout=(3, RSS_TIMEOUT_SECONDS), headers=headers)
        if response.status_code == 304:
            logger.debug("RSS_NOT_MODIFIED source=%s", source)
            with _state_lock:
                _feed_retry_after.pop(source, None)
                _feed_failures.pop(source, None)
            return []
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "")
            try:
                cooldown = min(RSS_MAX_COOLDOWN_SECONDS, max(60, int(retry_after)))
            except (TypeError, ValueError):
                cooldown = RSS_FAILURE_COOLDOWN_SECONDS
            with _state_lock:
                _host_retry_after[host] = time.monotonic() + cooldown
            raise requests.HTTPError("HTTP 429 rate limited", response=response)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise ValueError(f"RSS parse error: {getattr(parsed, 'bozo_exception', 'unknown')}")

        cache_headers = {}
        if response.headers.get("ETag"):
            cache_headers["If-None-Match"] = response.headers["ETag"]
        if response.headers.get("Last-Modified"):
            cache_headers["If-Modified-Since"] = response.headers["Last-Modified"]

        with _state_lock:
            _feed_cache_headers[source] = cache_headers
            _feed_retry_after.pop(source, None)
            _feed_failures.pop(source, None)
            _feed_failure_logged.discard(source)

        items = []
        for entry in parsed.entries[:limit_per_feed]:
            title = (entry.get("title") or "").strip()
            url = (entry.get("link") or "").strip()
            if not title or not url:
                continue
            items.append({
                "id": _make_id(url, title),
                "title": title,
                "source": source,
                "url": url,
                "summary": (entry.get("summary") or entry.get("description") or "")[:1200],
                "rss_image": _extract_rss_image(entry),
                "published_at": _published_at(entry),
                "source_domain": host,
            })
        logger.info("RSS_SOURCE_OK source=%s items=%d", source, len(items))
        return items
    except Exception as exc:
        with _state_lock:
            failures = _feed_failures.get(source, 0) + 1
            _feed_failures[source] = failures
            cooldown = min(
                RSS_MAX_COOLDOWN_SECONDS,
                RSS_FAILURE_COOLDOWN_SECONDS * (2 ** min(failures - 1, 4)),
            )
            _feed_retry_after[source] = time.monotonic() + cooldown
            first_log = source not in _feed_failure_logged
            _feed_failure_logged.add(source)
        if first_log:
            logger.warning(
                "RSS_SOURCE_FAIL source=%s host=%s cooldown_s=%d error=%s",
                source, host, cooldown, type(exc).__name__,
            )
        return []


def fetch_news(limit_per_feed: int = 3) -> list:
    """Collect news from all healthy configured feeds without serial blocking."""
    if not RSS_FEEDS:
        return []
    items = []
    workers = min(RSS_MAX_WORKERS, len(RSS_FEEDS))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="triada-rss") as pool:
        futures = {
            pool.submit(_fetch_one, source, url, limit_per_feed): source
            for source, url in RSS_FEEDS.items()
        }
        for future in as_completed(futures):
            source = futures[future]
            try:
                items.extend(future.result())
            except Exception:
                logger.exception("RSS_WORKER_FAIL source=%s", source)

    # Deduplicate syndicated copies while preserving publisher provenance.
    unique = {}
    for item in items:
        key = _make_id(item["url"], item["title"])
        unique.setdefault(key, item)
    result = list(unique.values())
    result.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    logger.info(
        "RSS_COLLECTION sources=%d healthy_items=%d configured=%d",
        len({item["source"] for item in result}), len(result), len(RSS_FEEDS),
    )
    return result


def fetch_breaking_news(limit_per_feed: int = 2) -> list:
    breaking_keywords = (
        "breaking", "urgent", "срочно", "flash", "alert", "emergency",
        "crisis", "crash", "collapse", "sanctions", "war", "attack",
        "recession", "default", "fed", "rate", "powell", "tariff",
        "inflation", "earnings", "bank", "central bank", "опек",
    )
    all_news = fetch_news(limit_per_feed)
    breaking = []
    for item in all_news:
        text = (item["title"] + " " + item["summary"]).lower()
        if any(keyword in text for keyword in breaking_keywords):
            breaking.append(item)
    return breaking if breaking else all_news[:2]


def get_source_health() -> dict:
    """Return a safe operational snapshot for diagnostics/tests."""
    now = time.monotonic()
    with _state_lock:
        return {
            "configured": len(RSS_FEEDS),
            "cooling_down": sum(until > now for until in _feed_retry_after.values()),
            "failed_sources": len(_feed_failures),
            "cached_validators": len(_feed_cache_headers),
        }
