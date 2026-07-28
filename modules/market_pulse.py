"""
Пульс рынка для закреплённого сообщения.

USD/RUB — через Yahoo Finance (yfinance, USDRUB=X): даёт актуальный курс
в любое время суток, а не только во время торгов на MOEX.

IMOEX — через MOEX ISS API:
  • marketdata.CURRENTVALUE — текущая цена (только во время торгов)
  • securities.PREVPRICE    — цена предыдущего закрытия (всегда доступна)
Таким образом IMOEX присутствует в закрепе всегда, с пометкой "(закр.)"
если биржа не торгует прямо сейчас.
"""
import logging
import datetime
import requests

logger = logging.getLogger(__name__)




def fetch_usd_rub() -> float | None:
    """Yahoo Finance USDRUB=X с явным временным диапазоном для обхода кэша.
    Каждый вызов запрашивает данные за последние 20 минут — новое окно
    означает новый запрос, не попадающий в кэш предыдущего обращения."""
    try:
        import yfinance as yf
        now = datetime.datetime.utcnow()
        start = now - datetime.timedelta(minutes=20)
        # Используем yf.download с явным start/end — обходит кэш Ticker.history
        data = yf.download(
            "USDRUB=X",
            start=start.strftime("%Y-%m-%d %H:%M:%S"),
            end=now.strftime("%Y-%m-%d %H:%M:%S"),
            interval="1m",
            progress=False,
            auto_adjust=True,
            multi_level_index=False,
        )
        if data is not None and not data.empty:
            close_col = "Close" if "Close" in data.columns else data.columns[0]
            price = float(data[close_col].iloc[-1])
            if price > 0:
                return round(price, 2)
        # Fallback: более широкое окно
        data2 = yf.download(
            "USDRUB=X",
            period="1d",
            interval="5m",
            progress=False,
            auto_adjust=True,
            multi_level_index=False,
        )
        if data2 is not None and not data2.empty:
            close_col = "Close" if "Close" in data2.columns else data2.columns[0]
            price = float(data2[close_col].iloc[-1])
            if price > 0:
                return round(price, 2)
        return None
    except Exception as e:
        logger.error(f"USD/RUB (yfinance) fetch error: {e}")
        return None


IMOEX_MARKETDATA_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/index"
    "/boards/SNDX/securities/IMOEX.json"
)
MOEX_TIMEOUT = 10


def _moex_first_row(block: dict) -> dict | None:
    if not block:
        return None
    columns = block.get("columns", [])
    data    = block.get("data", [])
    if not data:
        return None
    return dict(zip(columns, data[0]))


def fetch_imoex() -> dict | None:
    """MOEX ISS — индекс Мосбиржи IMOEX.

    Уровень 1: marketdata.CURRENTVALUE — текущая цена (только в торговые часы).
    Уровень 2: securities.PREVPRICE     — цена закрытия предыдущей сессии
               (всегда доступна, используется когда биржа закрыта).
    Возвращает dict с ключами value, change_pct, is_closed (bool).
    """
    try:
        resp = requests.get(
            IMOEX_MARKETDATA_URL,
            params={
                "iss.meta": "off",
                "marketdata.columns": "SECID,CURRENTVALUE,LASTTOPREVPRICE",
                "securities.columns": "SECID,PREVPRICE",
            },
            timeout=MOEX_TIMEOUT,
        )
        resp.raise_for_status()
        js = resp.json()

        md_row  = _moex_first_row(js.get("marketdata"))
        sec_row = _moex_first_row(js.get("securities"))

        current = md_row.get("CURRENTVALUE") if md_row else None
        change  = md_row.get("LASTTOPREVPRICE") if md_row else None
        prev    = sec_row.get("PREVPRICE") if sec_row else None

        if current is not None:
            return {"value": current, "change_pct": change, "is_closed": False}
        if prev is not None:
            return {"value": prev, "change_pct": None, "is_closed": True}
        return None

    except Exception as e:
        logger.error(f"IMOEX fetch error: {e}")
        return None


def build_pulse_text() -> str:
    """Текст закреплённого сообщения. Если данные недоступны — не выдумываем цифры."""
    usd_rub = fetch_usd_rub()
    imoex = fetch_imoex()

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    parts = []
    if usd_rub is not None:
        parts.append(f"USD/RUB <code>{usd_rub:,.2f}</code>")
    if imoex is not None:
        pct = imoex.get("change_pct")
        sign = "+" if (pct or 0) >= 0 else ""
        pct_str = f" ({sign}{pct:.2f}%)" if pct is not None else ""
        closed_mark = " <i>закр.</i>" if imoex.get("is_closed") else ""
        parts.append(f"IMOEX <code>{imoex['value']:,.2f}</code>{pct_str}{closed_mark}")

    if not parts:
        return "📌 Пульс рынка временно недоступен — обновим в следующий раз."

    return "📌 <b>Пульс рынка</b> · " + " · ".join(parts) + f"\nОбновлено {now.strftime('%H:%M МСК')}"
