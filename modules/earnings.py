"""
Дайджест отчётностей: предупреждение о скорой публикации квартального
отчёта + разбор факт/прогноз после публикации. Данные — через yfinance
(get_earnings_dates), уже зависимость проекта, ничего нового не добавляем.

Ограничение: даты отчётностей у yfinance надёжны в основном для крупных
американских компаний (биржи NYSE/NASDAQ), для российских эмитентов
(MOEX) эти данные обычно отсутствуют или ненадёжны — поэтому watchlist
сейчас только американский.
"""
import logging
import datetime
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

WATCHLIST = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "JPM"]


def _get_earnings_df(ticker: str) -> pd.DataFrame | None:
    try:
        df = yf.Ticker(ticker).get_earnings_dates(limit=8)
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        logger.error(f"get_earnings_dates error ({ticker}): {e}")
        return None


def check_upcoming(days_ahead: int = 3) -> list[dict]:
    """Компании из watchlist, которые отчитываются в ближайшие days_ahead дней."""
    now = pd.Timestamp.now(tz="UTC")
    horizon = now + pd.Timedelta(days=days_ahead)
    results = []

    for ticker in WATCHLIST:
        try:
            df = _get_earnings_df(ticker)
            if df is None:
                continue
            for idx, row in df.iterrows():
                event_date = idx if idx.tzinfo else idx.tz_localize("UTC")
                if now <= event_date <= horizon:
                    results.append({"ticker": ticker, "date": event_date})
                    break  # только ближайшая предстоящая дата
        except Exception as e:
            logger.error(f"check_upcoming error ({ticker}): {e}")
            continue

    results.sort(key=lambda x: x["date"])
    return results


def check_recent_results(days_back: int = 2) -> list[dict]:
    """Компании из watchlist, которые отчитались за последние days_back дней
    и у которых уже есть фактический результат (Reported EPS не пустой)."""
    now = pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(days=days_back)
    results = []

    for ticker in WATCHLIST:
        try:
            df = _get_earnings_df(ticker)
            if df is None:
                continue
            for idx, row in df.iterrows():
                event_date = idx if idx.tzinfo else idx.tz_localize("UTC")
                if not (cutoff <= event_date <= now):
                    continue
                reported = row.get("Reported EPS")
                if reported is None or (isinstance(reported, float) and pd.isna(reported)):
                    continue
                results.append({
                    "ticker": ticker,
                    "date": event_date,
                    "estimate": row.get("EPS Estimate"),
                    "reported": reported,
                    "surprise_pct": row.get("Surprise(%)"),
                })
                break
        except Exception as e:
            logger.error(f"check_recent_results error ({ticker}): {e}")
            continue

    results.sort(key=lambda x: x["date"], reverse=True)
    return results
