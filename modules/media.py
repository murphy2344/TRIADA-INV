import io
import logging
import os
import aiohttp
from config.config import PEXELS_API_KEY, PIXABAY_API_KEY, GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX

logger = logging.getLogger(__name__)

WIKIMEDIA_UA = "TRIADAInvestingBot/1.0 (https://t.me/triada_investing; bot@triada.inv)"

CATEGORY_LABELS = {
    "urgent":  "СРОЧНАЯ НОВОСТЬ",
    "hourly":  "НОВОСТИ ЗА ЧАС",
    "morning": "УТРЕННИЙ ОБЗОР",
    "evening": "ВЕЧЕРНИЙ ОБЗОР",
    "weekly":  "ИТОГИ НЕДЕЛИ",
    "monthly": "ИТОГИ МЕСЯЦА",
    "market":  "ФИНАНСОВЫЕ РЫНКИ",
}

# Стаб-файлы по категории. Если файл существует на диске — используем его
# вместо генерации Pillow-картинки.
STUB_FILES = {
    "urgent":  "assets/stubs/breaking.jpg",
    "hourly":  "assets/stubs/hourly.jpg",
    "morning": "assets/stubs/morning.jpg",
    "evening": "assets/stubs/evening.jpg",
    "weekly":  "assets/stubs/weekly.jpg",
    "monthly": "assets/stubs/monthly.jpg",
    "market":  "assets/stubs/breaking.jpg",
}

# Индекс-пульс рынка для дайджестов без конкретного тикера
DIGEST_CATEGORIES = {"hourly", "morning", "evening", "weekly", "monthly"}
DEFAULT_PULSE_TICKER = "^GSPC"


def _load_stub_file(post_category: str) -> bytes | None:
    """Читает статичный стаб-файл из assets/stubs/ если он существует."""
    path = STUB_FILES.get(post_category)
    if path and os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Could not read stub file {path}: {e}")
    return None


def _generate_pillow_fallback(post_category: str = "market", ticker: str | None = None) -> bytes | None:
    """Брендированная заглушка TRIADA INVESTING в стиле Apple Stocks.
    Вызывается только если статичный стаб-файл не найден на диске."""
    from PIL import Image, ImageDraw, ImageFont

    sparkline = None
    resolved_ticker = ticker
    if not resolved_ticker and post_category in DIGEST_CATEGORIES:
        resolved_ticker = DEFAULT_PULSE_TICKER

    if resolved_ticker:
        try:
            from modules.charting import get_sparkline_data
            sparkline = get_sparkline_data(resolved_ticker, period="5d")
        except Exception as e:
            logger.warning(f"Sparkline data unavailable for fallback card: {e}")

    try:
        img = Image.new("RGB", (1200, 675), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)

        try:
            font_ticker = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 46)
            font_price  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
            font_change = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
            font_label  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
            font_small  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except Exception:
            font_ticker = font_price = font_change = font_label = font_small = ImageFont.load_default()

        label = CATEGORY_LABELS.get(post_category, "ФИНАНСОВЫЕ РЫНКИ")

        if sparkline and len(sparkline["values"]) >= 2:
            values = sparkline["values"]
            pct = sparkline["change_pct"]
            last = sparkline["last"]
            is_up = pct >= 0
            color = (48, 209, 88) if is_up else (255, 69, 58)

            draw.text((60, 50), sparkline["ticker"], fill=(255, 255, 255), font=font_ticker)
            draw.text((60, 110), label, fill=(140, 140, 140), font=font_small)
            draw.text((60, 170), f"{last:,.2f}", fill=(255, 255, 255), font=font_price)
            sign = "+" if pct >= 0 else ""
            draw.text((60, 250), f"{sign}{pct:.2f}%", fill=color, font=font_change)

            chart_top, chart_bottom = 400, 620
            chart_left, chart_right = 60, 1140
            v_min, v_max = min(values), max(values)
            v_range = (v_max - v_min) or 1
            points = []
            for i, v in enumerate(values):
                x = chart_left + (chart_right - chart_left) * i / (len(values) - 1)
                y = chart_bottom - (v - v_min) / v_range * (chart_bottom - chart_top)
                points.append((x, y))
            draw.line(points, fill=color, width=4, joint="curve")
            fill_poly = points + [(chart_right, chart_bottom), (chart_left, chart_bottom)]
            overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.polygon(fill_poly, fill=color + (35,))
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(img)
        else:
            bbox = draw.textbbox((0, 0), label, font=font_label)
            tw = bbox[2] - bbox[0]
            draw.text(((1200 - tw) // 2, 320), label, fill=(220, 220, 220), font=font_label)

        wm = "TRIADA INVESTING"
        bbox2 = draw.textbbox((0, 0), wm, font=font_small)
        ww = bbox2[2] - bbox2[0]
        draw.text((1200 - ww - 30, 675 - 44), wm, fill=(90, 90, 90), font=font_small)

        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.error(f"Pillow fallback error: {e}")
        return None


async def _wikimedia_commons(query: str, session: aiohttp.ClientSession) -> str | None:
    try:
        params = {
            "action": "query", "format": "json",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrlimit": 5, "prop": "imageinfo",
            "iiprop": "url|mime", "iiurlwidth": 1200,
        }
        headers = {"User-Agent": WIKIMEDIA_UA}
        async with session.get(
            "https://commons.wikimedia.org/w/api.php",
            params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status != 200:
                return None
            data = await r.json()
            for page in data.get("query", {}).get("pages", {}).values():
                for ii in page.get("imageinfo", []):
                    mime = ii.get("mime", "")
                    thumb = ii.get("thumburl") or ii.get("url", "")
                    if mime.startswith("image/") and "svg" not in mime and thumb:
                        return thumb
    except Exception as e:
        logger.warning(f"Wikimedia Commons error: {e}")
    return None


async def _wikipedia_pageimage(query: str, session: aiohttp.ClientSession) -> str | None:
    try:
        headers = {"User-Agent": WIKIMEDIA_UA}
        base = "https://en.wikipedia.org/w/api.php"
        async with session.get(
            base,
            params={"action": "query", "format": "json", "list": "search",
                    "srsearch": query, "srlimit": 1},
            headers=headers, timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status != 200:
                return None
            results = (await r.json()).get("query", {}).get("search", [])
            if not results:
                return None
            title = results[0]["title"]

        async with session.get(
            base,
            params={"action": "query", "format": "json", "prop": "pageimages",
                    "titles": title, "pithumbsize": 1200},
            headers=headers, timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status != 200:
                return None
            for p in (await r.json()).get("query", {}).get("pages", {}).values():
                thumb = p.get("thumbnail", {}).get("source")
                if thumb:
                    return thumb
    except Exception as e:
        logger.warning(f"Wikipedia pageimage error: {e}")
    return None


async def _google_cse(query: str, session: aiohttp.ClientSession) -> str | None:
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_CX:
        return None
    try:
        async with session.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"key": GOOGLE_CSE_API_KEY, "cx": GOOGLE_CSE_CX,
                    "q": query, "searchType": "image", "num": 1, "safe": "active"},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status != 200:
                return None
            items = (await r.json()).get("items", [])
            if items:
                return items[0].get("link")
    except Exception as e:
        logger.warning(f"Google CSE error: {e}")
    return None


async def _pexels(query: str, session: aiohttp.ClientSession) -> str | None:
    if not PEXELS_API_KEY:
        return None
    try:
        async with session.get(
            f"https://api.pexels.com/v1/search?query={query}&per_page=5&orientation=landscape",
            headers={"Authorization": PEXELS_API_KEY},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status == 200:
                photos = (await r.json()).get("photos", [])
                if photos:
                    return photos[0]["src"]["large"]
    except Exception as e:
        logger.warning(f"Pexels error: {e}")
    return None


async def _pixabay(query: str, session: aiohttp.ClientSession) -> str | None:
    if not PIXABAY_API_KEY:
        return None
    try:
        async with session.get(
            f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}"
            f"&image_type=photo&orientation=horizontal&per_page=5",
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status == 200:
                hits = (await r.json()).get("hits", [])
                if hits:
                    return hits[0]["largeImageURL"]
    except Exception as e:
        logger.warning(f"Pixabay error: {e}")
    return None


async def get_photo(
    subject: str,
    subject_en: str | None = None,
    rss_image: str | None = None,
    post_category: str = "market",
    ticker: str | None = None,
) -> bytes | str | None:
    """
    Priority per spec:
    1. RSS article image
    2. Wikimedia Commons (subject_en preferred)
    3. Wikipedia page thumbnail
    4. Google CSE
    5. Pexels / Pixabay (if keys set)
    6. Static stub file from assets/stubs/ (если существует)
    7. Pillow-generated branded fallback (только если стаб-файла нет)
    """
    # Step 1
    if rss_image and rss_image.startswith("http"):
        logger.info(f"Media: RSS image for '{subject[:40]}'")
        return rss_image

    search_query = (subject_en.strip() if subject_en and subject_en.strip() else subject)

    async with aiohttp.ClientSession() as session:
        # Step 2
        result = await _wikimedia_commons(search_query, session)
        if result:
            logger.info(f"Media: Wikimedia for '{search_query[:40]}'")
            return result

        # Step 3
        result = await _wikipedia_pageimage(search_query, session)
        if result:
            logger.info(f"Media: Wikipedia for '{search_query[:40]}'")
            return result

        # Step 4
        result = await _google_cse(search_query, session)
        if result:
            logger.info(f"Media: Google CSE for '{search_query[:40]}'")
            return result

        # Step 5
        result = await _pexels(search_query, session)
        if result:
            logger.info(f"Media: Pexels for '{search_query[:40]}'")
            return result

        result = await _pixabay(search_query, session)
        if result:
            logger.info(f"Media: Pixabay for '{search_query[:40]}'")
            return result

    # Step 6 — статичный стаб-файл из assets/stubs/
    stub = _load_stub_file(post_category)
    if stub:
        logger.info(f"Media: static stub file for '{post_category}'")
        return stub

    # Step 7 — Pillow-генерация только если стаб-файла нет на диске
    logger.info(f"Media: Pillow fallback for '{search_query[:40]}'")
    return _generate_pillow_fallback(post_category, ticker=ticker)
