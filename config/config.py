import os

BOT_TOKEN      = os.getenv("BOT_TOKEN", "")
CHANNEL_ID     = os.getenv("CHANNEL_ID", "")
GROUP_CHAT_ID  = os.getenv("GROUP_CHAT_ID", "")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_ID       = os.getenv("ADMIN_ID", "")

GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL         = "llama-3.3-70b-versatile"
GROQ_FALLBACK_MODEL = "llama-3.1-8b-instant"

# Optional Telegram forum group / User API monitor
TG_API_ID = os.getenv("TG_API_ID", "")
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_SESSION_STRING = os.getenv("TG_SESSION_STRING", "")
TG_MONITOR_CHANNELS = os.getenv("TG_MONITOR_CHANNELS", "")

# FRED (Федеральный резервный банк Сент-Луиса) — экономический календарь.
# Бесплатно, без карты, мгновенная регистрация: fredaccount.stlouisfed.org/apikeys
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

PEXELS_API_KEY   = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY  = os.getenv("PIXABAY_API_KEY", "")
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_CX    = os.getenv("GOOGLE_CSE_CX", "")

# Optional market-data providers. The bot continues to use free yfinance
# fallbacks when these values are absent.
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
CHART_IMG_API_KEY = os.getenv("CHART_IMG_API_KEY", "")

# Upstash Redis — persistent dedup (free, no card needed: upstash.com)
# Falls back to SQLite if not configured
UPSTASH_REDIS_REST_URL   = os.getenv("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

DB_PATH = "data/bot.db"

# Глобальные финансовые и деловые RSS-ленты.
RSS_FEEDS = {
    "Reuters Business": "https://feeds.reuters.com/reuters/businessNews",
    "Investing.com":    "https://www.investing.com/rss/news.rss",
    "ForexLive":        "https://www.forexlive.com/feed/news",
    "CNBC Markets":     "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "WSJ Business":     "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
    "Bloomberg Markets": "https://feeds.bloomberg.com/markets/news.rss",
    "Bloomberg Politics": "https://feeds.bloomberg.com/politics/news.rss",
    "Reuters World":    "http://feeds.reuters.com/Reuters/worldNews",
    "Reuters Money":    "http://feeds.reuters.com/news/wealth",
    "MarketWatch":      "https://www.marketwatch.com/rss/topstories",
    "Financial Times":  "https://www.ft.com/?format=rss",
    "Abnormal Returns": "https://abnormalreturns.com/feed",
    "Ritholtz":         "https://ritholtz.com/feed",
    "Barron's":         "https://www.barrons.com/rss",
    "Seeking Alpha":    "https://seekingalpha.com/feed.xml",
}
