"""
Пульс рынка для закреплённого сообщения.

USD/RUB — через Yahoo Finance (yfinance, USDRUB=X): даёт актуальный курс
в любое время суток, а не только во время торгов на MOEX.

IMOEX — через yfinance (IMOEX.ME): та же логика — работает круглосуточно,
не зависит от доступности MOEX ISS API.
"""
import logging
import datetime

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


def fetch_imoex() -> dict | None:
    """IMOEX через yfinance (IMOEX.ME) — работает круглосуточно,
    не зависит от доступности MOEX ISS API."""
    try:
        import yfinance as yf
        ticker = yf.Ticker("IMOEX.ME")
        hist = ticker.history(period="2d", interval="1h", auto_adjust=True)
        if hist is None or hist.empty:
            # Fallback: более широкое окно
            hist = ticker.history(period="5d", interval="1d", auto_adjust=True)
        if hist is None or hist.empty:
            return None
        current = float(hist["Close"].iloc[-1])
        prev    = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
        change_pct = round((current - prev) / prev * 100, 2) if prev else None
        return {"value": round(current, 2), "change_pct": change_pct}
    except Exception as e:
        logger.error(f"IMOEX (yfinance) fetch error: {e}")
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
        parts.append(f"IMOEX <code>{imoex['value']:,.2f}</code>{pct_str}")

    if not parts:
        return "📌 Пульс рынка временно недоступен — обновим в следующий раз."

    return "📌 <b>Пульс рынка</b> · " + " · ".join(parts) + f"\nОбновлено {now.strftime('%H:%M МСК')}"
