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

# Extended watchlist for earnings tracking
WATCHLIST = [
    # Mega caps
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "BRK.B",
    # Large caps
    "JPM", "V", "MA", "WMT", "UNH", "JNJ", "PG", "XOM", "CVX", "BAC",
    # Tech
    "AMD", "INTC", "AVGO", "ORCL", "CRM", "ADBE", "CSCO", "QCOM",
    # Growth
    "NFLX", "DIS", "BABA", "NIO", "PLTR", "COIN", "SHOP",
]


def _get_earnings_df(ticker: str) -> pd.DataFrame | None:
    try:
        df = yf.Ticker(ticker).get_earnings_dates(limit=8)
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        logger.error(f"get_earnings_dates error ({ticker}): {e}")
        return None


def check_today() -> list[dict]:
    """Companies reporting today."""
    now = pd.Timestamp.now(tz="UTC")
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + pd.Timedelta(days=1)
    results = []

    for ticker in WATCHLIST:
        try:
            df = _get_earnings_df(ticker)
            if df is None:
                continue
            for idx, row in df.iterrows():
                event_date = idx if idx.tzinfo else idx.tz_localize("UTC")
                if today_start <= event_date < today_end:
                    estimate = row.get("EPS Estimate")
                    results.append({
                        "ticker": ticker,
                        "date": event_date,
                        "estimate": estimate,
                        "time": "BMO" if event_date.hour < 12 else "AMC"  # Before/After Market
                    })
                    break
        except Exception as e:
            logger.error(f"check_today error ({ticker}): {e}")
            continue

    results.sort(key=lambda x: x["date"])
    return results


def check_this_week() -> list[dict]:
    """Companies reporting this week (next 7 days)."""
    now = pd.Timestamp.now(tz="UTC")
    week_end = now + pd.Timedelta(days=7)
    results = []

    for ticker in WATCHLIST:
        try:
            df = _get_earnings_df(ticker)
            if df is None:
                continue
            for idx, row in df.iterrows():
                event_date = idx if idx.tzinfo else idx.tz_localize("UTC")
                if now <= event_date <= week_end:
                    estimate = row.get("EPS Estimate")
                    results.append({
                        "ticker": ticker,
                        "date": event_date,
                        "estimate": estimate,
                        "day_name": event_date.strftime("%A")
                    })
                    break
        except Exception as e:
            logger.error(f"check_this_week error ({ticker}): {e}")
            continue

    results.sort(key=lambda x: x["date"])
    return results


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

                estimate = row.get("EPS Estimate")
                surprise_pct = row.get("Surprise(%)")

                # Calculate beat/miss
                beat = None
                if estimate and reported:
                    if reported > estimate:
                        beat = "beat"
                    elif reported < estimate:
                        beat = "miss"
                    else:
                        beat = "inline"

                results.append({
                    "ticker": ticker,
                    "date": event_date,
                    "estimate": estimate,
                    "reported": reported,
                    "surprise_pct": surprise_pct,
                    "beat": beat,
                })
                break
        except Exception as e:
            logger.error(f"check_recent_results error ({ticker}): {e}")
            continue

    results.sort(key=lambda x: x["date"], reverse=True)
    return results

