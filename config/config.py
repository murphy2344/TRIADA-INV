import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN      = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID     = os.environ.get("CHANNEL_ID", "")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "")
ADMIN_ID       = os.environ.get("ADMIN_ID", "")

GROQ_API_KEY       = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL         = "llama-3.3-70b-versatile"
GROQ_FALLBACK_MODEL = "llama-3.1-8b-instant"

# Google Gemini — AI-критик, ДРУГАЯ модель для проверки рекомендаций Apollo.
# Бесплатно, без карты: aistudio.google.com/apikey
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

PEXELS_API_KEY   = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY  = os.environ.get("PIXABAY_API_KEY", "")
GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_CX    = os.environ.get("GOOGLE_CSE_CX", "")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Upstash Redis — persistent dedup (free, no card needed: upstash.com)
# Falls back to SQLite if not configured
UPSTASH_REDIS_REST_URL   = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

DB_PATH = "data/bot.db"

# ТОЛЬКО финансовые/деловые RSS-ленты (без общемировых — спорт, шоу-бизнес)
RSS_FEEDS = {
    "Reuters Business": "https://feeds.reuters.com/reuters/businessNews",
    "Investing.com":    "https://www.investing.com/rss/news.rss",
    "ForexLive":        "https://www.forexlive.com/feed/news",
    "CNBC Markets":     "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "WSJ Business":     "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
    "БКС Экспресс":     "https://bcs-express.ru/rss",
    "РБК Финансы":      "https://www.rbc.ru/rss/fin/",
}
