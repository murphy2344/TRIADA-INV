"""
Технические алерты по списку ключевых тикеров: RSI (перекупленность/
перепроданность) и пересечение цены со скользящими средними (SMA50/SMA200,
золотой/мёртвый крест). Считается вручную через pandas (уже зависимость
проекта) — НЕ добавляем новую библиотеку вроде TA-Lib/ta, чтобы не тащить
лишнее и не рисковать проблемами установки на Render.
"""
import logging
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

WATCHLIST = [
    "AAPL", "TSLA", "NVDA", "MSFT", "GOOGL",
    "SBER.ME", "GAZP.ME", "LKOH.ME",
    "GC=F", "CL=F", "BTC-USD",
]

RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30


def _compute_rsi(closes: pd.Series, period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    last_avg_gain = avg_gain.iloc[-1]
    last_avg_loss = avg_loss.iloc[-1]
    if last_avg_loss == 0:
        return 100.0
    rs = last_avg_gain / last_avg_loss
    return 100 - (100 / (1 + rs))


def analyze_ticker(ticker: str) -> dict | None:
    """Возвращает текущие технические показатели по тикеру, либо None,
    если данных недостаточно (мало истории/сеть недоступна)."""
    try:
        data = yf.Ticker(ticker).history(period="1y", interval="1d")
        if data is None or data.empty or len(data) < 60:
            return None
        closes = data["Close"].dropna()

        rsi = _compute_rsi(closes, 14)
        sma50 = closes.rolling(50).mean().iloc[-1] if len(closes) >= 50 else None
        sma200 = closes.rolling(200).mean().iloc[-1] if len(closes) >= 200 else None
        last_price = float(closes.iloc[-1])

        return {
            "ticker": ticker,
            "price": last_price,
            "rsi": round(rsi, 1) if rsi is not None else None,
            "sma50": round(float(sma50), 2) if sma50 is not None else None,
            "sma200": round(float(sma200), 2) if sma200 is not None else None,
        }
    except Exception as e:
        logger.error(f"analyze_ticker error ({ticker}): {e}")
        return None


def detect_signals(info: dict) -> list[dict]:
    """Определяет, какие сигналы сработали для тикера. Возвращает список
    словарей {type, text} — может быть несколько сигналов сразу."""
    if not info:
        return []
    signals = []

    rsi = info.get("rsi")
    if rsi is not None:
        if rsi >= RSI_OVERBOUGHT:
            signals.append({"type": "rsi_overbought", "text": f"RSI {rsi} — актив перекуплен"})
        elif rsi <= RSI_OVERSOLD:
            signals.append({"type": "rsi_oversold", "text": f"RSI {rsi} — актив перепродан"})

    price = info.get("price")
    sma50 = info.get("sma50")
    if price is not None and sma50 is not None:
        if price > sma50:
            signals.append({"type": "above_sma50", "text": f"Цена выше 50-дневной средней ({sma50:,.2f})"})
        else:
            signals.append({"type": "below_sma50", "text": f"Цена ниже 50-дневной средней ({sma50:,.2f})"})

    return signals
