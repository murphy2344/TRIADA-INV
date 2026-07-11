import feedparser
import hashlib
import logging
from config.config import RSS_FEEDS

logger = logging.getLogger(__name__)

def _make_id(url: str, title: str) -> str:
    return hashlib.md5(f"{url}{title}".encode()).hexdigest()

def _extract_rss_image(entry) -> str | None:
    # 1. media_content (most common in news feeds)
    media_content = entry.get("media_content", [])
    for mc in media_content:
        url = mc.get("url", "")
        medium = mc.get("medium", "")
        if url and (medium == "image" or url.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))):
            return url

    # 2. media_thumbnail
    media_thumb = entry.get("media_thumbnail", [])
    for mt in media_thumb:
        url = mt.get("url", "")
        if url:
            return url

    # 3. enclosures with image mime type
    for enc in entry.get("enclosures", []):
        mime = enc.get("type", "")
        url = enc.get("url", "")
        if url and mime.startswith("image/"):
            return url

    # 4. links with image rel
    for link in entry.get("links", []):
        mime = link.get("type", "")
        url = link.get("href", "")
        if url and mime.startswith("image/"):
            return url

    return None

def fetch_news(limit_per_feed: int = 3) -> list:
    items = []
    for source, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:limit_per_feed]:
                title = entry.get("title", "").strip()
                url = entry.get("link", "")
                summary = entry.get("summary", "")
                if not title or not url:
                    continue
                items.append({
                    "id": _make_id(url, title),
                    "title": title,
                    "source": source,
                    "url": url,
                    "summary": summary[:500],
                    "rss_image": _extract_rss_image(entry),
                })
        except Exception as e:
            logger.error(f"RSS fetch error ({source}): {e}")
    return items

def fetch_breaking_news(limit_per_feed: int = 2) -> list:
    breaking_keywords = [
        "breaking", "urgent", "срочно", "flash", "alert", "emergency",
        "crisis", "crash", "collapse", "sanctions", "war", "attack",
        "recession", "default", "fed", "rate", "powell", "trump", "опек"
    ]
    all_news = fetch_news(limit_per_feed)
    breaking = []
    for item in all_news:
        text = (item["title"] + " " + item["summary"]).lower()
        if any(kw in text for kw in breaking_keywords):
            breaking.append(item)
    return breaking if breaking else all_news[:2]
