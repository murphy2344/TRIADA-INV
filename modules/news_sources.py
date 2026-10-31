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
import re
import threading
import time
import requests

from config.config import RSS_FEEDS, FINNHUB_API_KEY

logger = logging.getLogger(__name__)

_RUSSIAN_MARKET_STORY = re.compile(
    r"\\b(?:MOEX|IMOEX|RTS\\s+index|Russian stocks|Russia stocks|Russian equities|"
    r"Russian stock market|Moscow Exchange|MICEX|RUB|ruble|rouble)\\b",
    re.IGNORECASE,
)


def is_excluded_russian_market_story(item: dict) -> bool:
    """Exclude Russian exchange/currency coverage, but retain geopolitics affecting global markets."""
    text = f"{item.get('title', '')} {item.get('summary', '')}"
    return bool(_RUSSIAN_MARKET_STORY.search(text))

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
# Keep the last successful payload so conditional 304 responses and transient
# provider failures do not make the entire news cycle appear empty.
_feed_items_cache: dict[str, list[dict]] = {}
_feed_last_success: dict[str, float] = {}
_state_lock = threading.Lock()
_finnhub_cache = (0.0, [])
_FINNHUB_CACHE_SECONDS = 300
_finnhub_lock = threading.Lock()


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
            return [dict(item) for item in _feed_items_cache.get(source, [])[:limit_per_feed]]
        headers = {"User-Agent": RSS_USER_AGENT, **_feed_cache_headers.get(source, {})}

    try:
        response = requests.get(feed_url, timeout=(3, RSS_TIMEOUT_SECONDS), headers=headers)
        if response.status_code == 304:
            logger.debug("RSS_NOT_MODIFIED source=%s", source)
            with _state_lock:
                _feed_retry_after.pop(source, None)
                _feed_failures.pop(source, None)
                cached = [dict(item) for item in _feed_items_cache.get(source, [])]
            logger.debug("RSS_CACHE_REUSED source=%s items=%d", source, len(cached))
            return cached[:limit_per_feed]
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
        with _state_lock:
            _feed_cache_headers[source] = cache_headers
            _feed_items_cache[source] = [dict(item) for item in items]
            _feed_last_success[source] = time.monotonic()
            _feed_retry_after.pop(source, None)
            _feed_failures.pop(source, None)
            _feed_failure_logged.discard(source)
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
        # Serve the last known-good payload during an outage. Downstream
        # publication deduplication prevents reposting already handled items.
        with _state_lock:
            cached = [dict(item) for item in _feed_items_cache.get(source, [])]
        if cached:
            logger.info("RSS_STALE_CACHE_USED source=%s items=%d", source, len(cached[:limit_per_feed]))
        return cached[:limit_per_feed]



def _fetch_finnhub_general_news():
    """Optional second global-news provider; cached to conserve API quota."""
    global _finnhub_cache
    if not FINNHUB_API_KEY:
        return []
    now = time.monotonic()
    with _finnhub_lock:
        if now - _finnhub_cache[0] < _FINNHUB_CACHE_SECONDS:
            return list(_finnhub_cache[1])
        try:
            response = requests.get(
                "https://finnhub.io/api/v1/news",
                params={"category": "general", "token": FINNHUB_API_KEY},
                timeout=(3, RSS_TIMEOUT_SECONDS),
                headers={"User-Agent": RSS_USER_AGENT},
            )
            response.raise_for_status()
            payload = response.json()
            items = []
            for article in payload if isinstance(payload, list) else []:
                title = (article.get("headline") or "").strip()
                url = (article.get("url") or "").strip()
                if not title or not url:
                    continue
                try:
                    published = datetime.fromtimestamp(
                        int(article.get("datetime")), timezone.utc
                    ).isoformat()
                except (TypeError, ValueError, OSError, OverflowError):
                    published = ""
                items.append({
                    "id": _make_id(url, title),
                    "title": title,
                    "source": article.get("source") or "Finnhub",
                    "url": url,
                    "summary": (article.get("summary") or "")[:1200],
                    "rss_image": article.get("image") or None,
                    "published_at": published,
                    "source_domain": urlparse(url).netloc.lower(),
                })
            _finnhub_cache = (time.monotonic(), items[:80])
            logger.info("NEWS_PROVIDER_OK provider=Finnhub items=%d", len(items))
            return list(_finnhub_cache[1])
        except Exception as exc:
            logger.warning("NEWS_PROVIDER_FAIL provider=Finnhub error=%s", type(exc).__name__)
            _finnhub_cache = (time.monotonic() - (_FINNHUB_CACHE_SECONDS - 90), [])
            return []


def _title_tokens(title):
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "after", "before",
        "says", "said", "will", "into", "over", "about", "после", "перед", "для",
        "что", "как", "это",
    }
    tokens = set()
    for word in (title or "").lower().replace("-", " ").split():
        token = "".join(char for char in word if char.isalnum())
        if len(token) > 2 and token not in stop:
            tokens.add(token)
    return tokens


def _attach_corroborating_sources(items):
    """Attach distinct publishers for strongly similar headlines."""
    token_sets = [_title_tokens(item.get("title", "")) for item in items]
    for index, item in enumerate(items):
        domains = {item.get("source_domain") or item.get("source", "")}
        sources = {item.get("source", "")}
        own_tokens = token_sets[index]
        if len(own_tokens) >= 3:
            for other_index, other in enumerate(items):
                if index == other_index or not token_sets[other_index]:
                    continue
                other_domain = other.get("source_domain") or other.get("source", "")
                if other_domain in domains:
                    continue
                intersection = len(own_tokens & token_sets[other_index])
                union = len(own_tokens | token_sets[other_index])
                if union and intersection / union >= 0.62:
                    domains.add(other_domain)
                    sources.add(other.get("source", ""))
        item["corroborating_sources"] = sorted(source for source in sources if source)
        item["source_count"] = len(domains)

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

    # Merge RSS and Finnhub before deduplication so syndicated copies are not
    # processed twice and publisher provenance can be retained.
    items.extend(_fetch_finnhub_general_news())
    before_scope_filter = len(items)
    items = [item for item in items if not is_excluded_russian_market_story(item)]
    excluded_count = before_scope_filter - len(items)
    if excluded_count:
        logger.info("NEWS_SCOPE_FILTERED russian_market_items=%d", excluded_count)
    unique = {}
    for item in items:
        key = _make_id(item["url"], item["title"])
        unique.setdefault(key, item)
    result = list(unique.values())
    _attach_corroborating_sources(result)
    result.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    logger.info(
        "RSS_COLLECTION sources=%d healthy_items=%d configured=%d",
        len({item["source"] for item in result}), len(result), len(RSS_FEEDS),
    )
    return result


def fetch_breaking_news(limit_per_feed: int = 2, items: list[dict] | None = None) -> list:
    """Select a small, priority-ranked slice from the durable pending queue."""
    urgent_keywords = (
        "breaking", "urgent", "flash", "emergency", "crisis", "crash",
        "collapse", "default", "war", "attack", "sanctions", "recession",
    )
    high_impact_keywords = (
        "fed", "powell", "central bank", "rate decision", "inflation", "cpi",
        "jobs report", "earnings", "tariff", "opec", "bank failure",
    )
    all_news = items if items is not None else fetch_news(limit_per_feed)
    all_news = [item for item in all_news if not is_excluded_russian_market_story(item)]
    scored = []
    for item in all_news:
        headline = (str(item.get("title") or "") + " " + str(item.get("summary") or "")).lower()
        score = 3 if any(word in headline for word in urgent_keywords) else (
            2 if any(word in headline for word in high_impact_keywords) else 0
        )
        scored.append((score, str(item.get("published_at") or ""), item))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    selected = [row[2] for row in scored[:max(1, limit_per_feed)]]
    return selected


def get_source_health() -> dict:
    """Return a safe operational snapshot for diagnostics/tests."""
    now = time.monotonic()
    with _state_lock:
        return {
            "configured": len(RSS_FEEDS),
            "cooling_down": sum(until > now for until in _feed_retry_after.values()),
            "failed_sources": len(_feed_failures),
            "cached_validators": len(_feed_cache_headers),
            "cached_feeds": len(_feed_items_cache),
            "feeds_with_payload": sum(bool(items) for items in _feed_items_cache.values()),
            "last_success_age_seconds": {
                source: round(max(0.0, now - updated), 1)
                for source, updated in _feed_last_success.items()
            },
        }
