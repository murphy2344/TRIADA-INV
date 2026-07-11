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


def _generate_pillow_fallback(post_category: str = "market") -> bytes | None:
    """Generate branded TRIADA INVESTING placeholder (1200x675 JPG) via Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1200, 675), color=(10, 10, 10))
        draw = ImageDraw.Draw(img)

        cx, cy = 600, 280
        size = 110
        top = (cx, cy - size)
        bl  = (cx - size, cy + size)
        br  = (cx + size, cy + size)
        for p1, p2 in [(top, bl), (bl, br), (br, top)]:
            draw.line([p1, p2], fill=(255, 255, 255), width=3)

        label = CATEGORY_LABELS.get(post_category, "ФИНАНСОВЫЕ РЫНКИ")
        try:
            font_big   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except Exception:
            font_big = font_small = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), label, font=font_big)
        tw = bbox[2] - bbox[0]
        draw.text((cx - tw // 2, cy + size + 40), label, fill=(220, 220, 220), font=font_big)

        wm = "TRIADA INVESTING"
        bbox2 = draw.textbbox((0, 0), wm, font=font_small)
        ww = bbox2[2] - bbox2[0]
        draw.text((1200 - ww - 20, 675 - 34), wm, fill=(80, 80, 80), font=font_small)

        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
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
) -> bytes | str | None:
    """
    Priority per spec:
    1. RSS article image
    2. Wikimedia Commons (subject_en preferred)
    3. Wikipedia page thumbnail (subject_en preferred)
    4. Google CSE (subject_en preferred)
    5. Pexels / Pixabay (if keys set)
    6. Pillow-generated branded fallback
    """
    # Step 1
    if rss_image and rss_image.startswith("http"):
        logger.info(f"Media: RSS image for '{subject[:40]}'")
        return rss_image

    # Use English query for external search; fallback to Russian if not available
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

    # Step 6
    logger.info(f"Media: Pillow fallback for '{search_query[:40]}'")
    return _generate_pillow_fallback(post_category)
