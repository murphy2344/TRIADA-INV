"""
Тепловая карта секторов — через ETF-прокси (стандартный способ отслеживать
ротацию капитала между секторами). Переиспользует charting.get_sparkline_data
(тот же вызов, что и для чип-строки/заглушек) — ничего нового в плане
источников данных не вводим.
"""
import io
import logging

logger = logging.getLogger(__name__)

SECTORS = {
    "XLK":  "Технологии",
    "XLE":  "Энергетика",
    "XLF":  "Финансы",
    "XLV":  "Здравоохранение",
    "XLY":  "Потреб. (циклич.)",
    "XLP":  "Потреб. (защитн.)",
    "XLI":  "Промышленность",
    "XLB":  "Материалы",
    "XLU":  "Коммунальные",
    "XLRE": "Недвижимость",
    "XLC":  "Коммуникации",
}


def fetch_sector_changes() -> dict:
    """{тикер_ETF: % изменения за день}. Секторы, для которых данные не
    получены, просто отсутствуют в результате — не выдумываем цифры."""
    from modules.charting import get_sparkline_data

    result = {}
    for etf in SECTORS:
        try:
            data = get_sparkline_data(etf, period="1d")
            if data and data.get("change_pct") is not None:
                result[etf] = data["change_pct"]
        except Exception as e:
            logger.error(f"Sector fetch error ({etf}): {e}")
            continue
    return result


def generate_heatmap_image(changes: dict) -> bytes | None:
    """Простая тепловая карта — сетка прямоугольников, цвет по знаку/силе
    изменения (в стиле Apple: зелёный/красный, тёмный фон)."""
    if not changes:
        return None

    from PIL import Image, ImageDraw, ImageFont

    try:
        cols, rows = 4, 3
        cell_w, cell_h = 290, 210
        margin = 10
        width = cols * cell_w
        height = rows * cell_h

        img = Image.new("RGB", (width, height), color=(10, 10, 10))
        draw = ImageDraw.Draw(img)
        try:
            font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
            font_pct = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
        except Exception:
            font_name = font_pct = ImageFont.load_default()

        max_abs = max(abs(v) for v in changes.values()) or 1
        items = sorted(changes.items(), key=lambda kv: kv[1], reverse=True)

        for idx, (etf, pct) in enumerate(items[:cols * rows]):
            row, col = divmod(idx, cols)
            x0 = col * cell_w + margin
            y0 = row * cell_h + margin
            x1 = (col + 1) * cell_w - margin
            y1 = (row + 1) * cell_h - margin

            intensity = min(abs(pct) / max_abs, 1.0)
            if pct >= 0:
                color = (int(10 + 20 * (1 - intensity)), int(60 + 149 * intensity), int(40 + 40 * (1 - intensity)))
            else:
                color = (int(60 + 195 * intensity), int(20 + 20 * (1 - intensity)), int(20 + 20 * (1 - intensity)))

            draw.rectangle([x0, y0, x1, y1], fill=color)

            label = SECTORS.get(etf, etf)
            sign = "+" if pct >= 0 else ""
            draw.text((x0 + 14, y0 + 14), label, fill=(255, 255, 255), font=font_name)
            draw.text((x0 + 14, y0 + 50), f"{sign}{pct:.2f}%", fill=(255, 255, 255), font=font_pct)

        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        buf.seek(0)
        return buf.getvalue()
    except Exception as e:
        logger.error(f"generate_heatmap_image error: {e}")
        return None
