import io
import logging
import os
import re
import time
import requests
import threading
from config.config import CHART_IMG_API_KEY

logger = logging.getLogger(__name__)

FINVIZ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://finviz.com/",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
}

TICKER_ALIASES = {
    "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "ethereum": "ETH-USD", "eth": "ETH-USD",
    "gold": "GC=F", "золото": "GC=F",
    "oil": "CL=F", "нефть": "CL=F", "brent": "BZ=F",
    "sp500": "^GSPC", "s&p": "^GSPC", "spx": "^GSPC",
    "nasdaq": "^IXIC", "dow": "^DJI",
    "apple": "AAPL", "tesla": "TSLA", "nvidia": "NVDA",
    "microsoft": "MSFT", "amazon": "AMZN", "google": "GOOGL",
    "meta": "META", "eurusd": "EURUSD=X", "usd": "DX-Y.NYB",
    "серебро": "SI=F", "silver": "SI=F",
    "jpmorgan": "JPM", "goldman": "GS", "exxon": "XOM",
}

# Finviz uses different ticker format for some instruments

# TradingView symbols differ from Yahoo Finance symbols. Explicit mappings avoid
# sending Yahoo-only suffixes (for example "=F" and "=X") to Chart-IMG.
CHART_IMG_SYMBOL_MAP = {
    "GC=F": "COMEX:GC1!",
    "CL=F": "NYMEX:CL1!",
    "BZ=F": "ICEEUR:BRN1!",
    "SI=F": "COMEX:SI1!",
    "EURUSD=X": "FX:EURUSD",
    "GBPUSD=X": "FX:GBPUSD",
    "JPY=X": "FX:USDJPY",
    "RUB=X": "FX:USDRUB",
    "USDRUB=X": "FX:USDRUB",
    "DX-Y.NYB": "TVC:DXY",
    "BTC-USD": "BINANCE:BTCUSDT",
    "ETH-USD": "BINANCE:ETHUSDT",
    "^GSPC": "SP:SPX",
    "^IXIC": "NASDAQ:IXIC",
    "^DJI": "DJ:DJI",
    "^RUT": "RUSSELL:RUT",
    "^VIX": "CBOE:VIX",
    "^TNX": "TVC:US10Y",
    "^IRX": "TVC:US13W",
    "^FTSE": "CAPITALCOM:UK100",
    "^GDAXI": "XETR:DAX",
    "^N225": "TVC:NI225",
    "000001.SS": "SSE:000001",
    "AAPL": "NASDAQ:AAPL",
    "MSFT": "NASDAQ:MSFT",
    "NVDA": "NASDAQ:NVDA",
    "GOOGL": "NASDAQ:GOOGL",
    "AMZN": "NASDAQ:AMZN",
    "META": "NASDAQ:META",
    "TSLA": "NASDAQ:TSLA",
    "JPM": "NYSE:JPM",
    "GS": "NYSE:GS",
    "XOM": "NYSE:XOM",
    "BRK.B": "NYSE:BRK.B",
}


def chart_img_symbol(ticker: str) -> str:
    """Translate a Yahoo symbol to a TradingView exchange-qualified symbol."""
    return CHART_IMG_SYMBOL_MAP.get(ticker, ticker)


FINVIZ_TICKER_MAP = {
    "GC=F": "GC",   # Gold futures
    "CL=F": "CL",   # Oil futures
    "BZ=F": "BZ",   # Brent futures
    "SI=F": "SI",   # Silver futures
    "EURUSD=X": "EURUSD",
    "DX-Y.NYB": "DX",
    "RUB=X": None,  # Not on Finviz
    "BTC-USD": "BTCUSD",
    "ETH-USD": "ETHUSD",
}

# Минимальный размер реального графика Finviz в байтах.
# "Chart not available" — это маленький GIF/PNG (~2-4 KB).
# Реальный дневной график — обычно 30–80 KB.
_FINVIZ_MIN_VALID_BYTES = 8_000


def resolve_ticker(raw: str) -> str | None:
    if not raw:
        return None
    lower = raw.lower().strip()
    if lower in TICKER_ALIASES:
        return TICKER_ALIASES[lower]
    return raw.upper()


def _finviz_chart(ticker: str) -> bytes | None:
    """Fetch chart from Finviz. Возвращает None если Finviz вернул
    заглушку 'Chart not available' (детектируем по размеру < 8 KB)."""
    finviz_ticker = FINVIZ_TICKER_MAP.get(ticker, ticker)
    if finviz_ticker is None:
        return None

    url = f"https://finviz.com/chart.ashx?t={finviz_ticker}&ty=c&ta=1&p=d&s=l"
    for attempt in range(2):
        try:
            r = requests.get(url, headers=FINVIZ_HEADERS, timeout=10)
            ct = r.headers.get("Content-Type", "")
            if r.status_code == 200 and ct.startswith("image/"):
                # Проверяем размер: заглушка "Chart not available" очень маленькая
                if len(r.content) < _FINVIZ_MIN_VALID_BYTES:
                    logger.warning(
                        f"Finviz returned placeholder for {finviz_ticker} "
                        f"({len(r.content)} bytes < {_FINVIZ_MIN_VALID_BYTES}), using fallback"
                    )
                    return None
                logger.info(f"Finviz chart OK for {finviz_ticker} ({len(r.content)} bytes)")
                return r.content
            else:
                logger.warning(f"Finviz attempt {attempt+1}: status={r.status_code}, ct={ct}")
                if attempt == 0:
                    time.sleep(1.5)
        except Exception as e:
            logger.warning(f"Finviz attempt {attempt+1} error: {e}")
            if attempt == 0:
                time.sleep(1.5)
    return None


def _yfinance_chart(ticker: str, period: str = "5d") -> bytes | None:
    # Heavy optional libraries are imported only when a chart is actually needed.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    """Fallback: свой график в стиле Apple Stocks —
    тёмный фон, крупная цена/% сверху, тонкая area-заливка под линией."""
    sparkline = get_sparkline_data(ticker, period)
    if not sparkline:
        return None
    fig = None
    try:
        values = sparkline["values"]
        last = sparkline["last"]
        pct = sparkline["change_pct"]
        is_up = pct >= 0
        color = "#30D158" if is_up else "#FF453A"  # Apple Stocks green/red

        fig, ax = plt.subplots(figsize=(10, 5.6), dpi=150)
        fig.patch.set_facecolor("#000000")
        ax.set_facecolor("#000000")

        x = range(len(values))
        ax.plot(x, values, color=color, linewidth=2.2, solid_capstyle="round")
        ax.fill_between(x, values, min(values), alpha=0.15, color=color)

        ax.axis("off")

        sign = "+" if pct >= 0 else ""
        fig.text(0.04, 0.92, ticker, color="#ffffff", fontsize=26, fontweight="bold", va="top")
        fig.text(0.04, 0.78, f"{last:,.2f}", color="#ffffff", fontsize=34, fontweight="bold", va="top")
        fig.text(0.04, 0.66, f"{sign}{pct:.2f}%", color=color, fontsize=20, fontweight="bold", va="top")
        fig.text(0.97, 0.04, "TRIADA INVESTING", ha="right", va="bottom",
                 fontsize=10, color="#555555")

        plt.tight_layout(rect=[0, 0.02, 1, 0.98])

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
        buf.seek(0)
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        if fig is not None:
            plt.close(fig)
        logger.error(f"yfinance Apple-style chart error ({ticker}): {e}")
        return None


def _chart_img_error_detail(response, api_key: str) -> str:
    """Return a short, secret-safe diagnostic from a Chart-IMG error response."""
    content_type = response.headers.get("Content-Type", "unknown").split(";", 1)[0]
    detail = ""
    if "json" in content_type.lower():
        try:
            payload = response.json()
            if isinstance(payload, dict):
                for field in ("message", "error", "detail", "code"):
                    value = payload.get(field)
                    if isinstance(value, (str, int, float)):
                        detail = str(value)
                        break
        except (ValueError, TypeError):
            pass
    if api_key:
        detail = detail.replace(api_key, "[REDACTED]")
    detail = re.sub(r"(?i)(bearer\s+)\S+", r"\1[REDACTED]", detail)
    detail = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,;]+", r"\1[REDACTED]", detail)
    detail = re.sub(r"[\r\n\t]+", " ", detail).strip()[:180]
    return f"content_type={content_type}, detail={detail or 'no safe error message provided'}"


def _chart_img(ticker: str) -> bytes | None:
    """Chart-IMG v1 TradingView image. Fail safely and log non-secret diagnostics."""
    if not CHART_IMG_API_KEY:
        logger.debug("Chart-IMG skipped: CHART_IMG_API_KEY is not configured")
        return None
    try:
        response = requests.get(
            "https://api.chart-img.com/v1/tradingview/advanced-chart",
            params={"symbol": chart_img_symbol(ticker), "interval": "1d"},
            # v1 uses Bearer authentication; x-api-key is documented for v2.
            headers={
                "Authorization": f"Bearer {CHART_IMG_API_KEY}",
                "Accept": "image/png",
            },
            timeout=20,
        )
        content_type = response.headers.get("Content-Type", "")
        if response.ok and content_type.lower().startswith("image/") and (
            response.content.startswith(b"\x89PNG\r\n\x1a\n")
            or response.content.startswith(b"\xff\xd8\xff")
        ):
            logger.info("Chart-IMG chart OK for %s (%s)", ticker, content_type.split(";", 1)[0])
            return response.content

        diagnostic = _chart_img_error_detail(response, CHART_IMG_API_KEY)
        logger.warning(
            "Chart-IMG failed for %s: HTTP %s; %s",
            ticker, response.status_code, diagnostic,
        )
    except Exception as exc:
        logger.warning("Chart-IMG request error for %s: %s", ticker, type(exc).__name__)
    return None


# Yahoo Finance sometimes rate-limits or returns empty history while its crumb
# endpoint is unavailable. A short process-wide cooldown prevents every scheduled
# signal from repeating the same failing request. It never fabricates prices.
_YFINANCE_COOLDOWN_UNTIL = 0.0
_YFINANCE_COOLDOWN_REASON = ""
_YFINANCE_COOLDOWN_LOGGED = False
_YFINANCE_COOLDOWN_SECONDS = 120
_YFINANCE_RATE_LIMIT_SECONDS = 600
_YFINANCE_LOCK = threading.Lock()
# Empty history is usually symbol-specific (market closed / unsupported ticker),
# so it must not pause every other instrument. Keep this cache bounded.
_YFINANCE_SYMBOL_COOLDOWNS: dict[str, float] = {}
_YFINANCE_SYMBOL_COOLDOWN_SECONDS = 300
_YFINANCE_SYMBOL_COOLDOWN_MAX_ENTRIES = 256


def _set_yfinance_symbol_cooldown(ticker: str, now: float | None = None) -> None:
    """Store a symbol-specific failure cooldown in a bounded cache.

    Expired entries are pruned on writes; if the cache is still full, evict
    the entry that expires first before adding another ticker.
    Caller holds _YFINANCE_LOCK.
    """
    if now is None:
        now = time.monotonic()
    expired = [
        symbol for symbol, expires_at in _YFINANCE_SYMBOL_COOLDOWNS.items()
        if expires_at <= now
    ]
    for symbol in expired:
        _YFINANCE_SYMBOL_COOLDOWNS.pop(symbol, None)

    if ticker not in _YFINANCE_SYMBOL_COOLDOWNS and (
        len(_YFINANCE_SYMBOL_COOLDOWNS) >= _YFINANCE_SYMBOL_COOLDOWN_MAX_ENTRIES
    ):
        oldest = min(_YFINANCE_SYMBOL_COOLDOWNS, key=_YFINANCE_SYMBOL_COOLDOWNS.get)
        _YFINANCE_SYMBOL_COOLDOWNS.pop(oldest, None)

    _YFINANCE_SYMBOL_COOLDOWNS[ticker] = now + _YFINANCE_SYMBOL_COOLDOWN_SECONDS


def _fetch_yfinance_history(
    ticker: str,
    period: str | None = "1d",
    interval: str | None = None,
    *,
    start=None,
    end=None,
):
    """Fetch Yahoo history through one process-wide lock and shared cooldown.

    Use either a period or an explicit start/end range. All automated Yahoo
    history requests should use this helper so provider failures are shared.
    """
    global _YFINANCE_COOLDOWN_UNTIL, _YFINANCE_COOLDOWN_REASON
    global _YFINANCE_COOLDOWN_LOGGED

    import yfinance as yf

    with _YFINANCE_LOCK:
        now = time.monotonic()
        symbol_cooldown = _YFINANCE_SYMBOL_COOLDOWNS.get(ticker, 0.0)
        if now < symbol_cooldown:
            return None
        if symbol_cooldown:
            _YFINANCE_SYMBOL_COOLDOWNS.pop(ticker, None)
        if now < _YFINANCE_COOLDOWN_UNTIL:
            if not _YFINANCE_COOLDOWN_LOGGED:
                logger.warning(
                    "Yahoo Finance requests paused for %.0fs after provider failure (%s)",
                    _YFINANCE_COOLDOWN_UNTIL - now,
                    _YFINANCE_COOLDOWN_REASON or "unavailable data",
                )
                _YFINANCE_COOLDOWN_LOGGED = True
            return None

        # yfinance may log a crumb 429 and still return partial data instead
        # of raising. Capture that warning so every caller shares the cooldown.
        class _CrumbRateLimitCapture(logging.Handler):
            rate_limited = False

            def emit(self, record):
                message = record.getMessage().lower()
                # yfinance can emit auth failures at ERROR level without the
                # word "rate limit" (for example "HTTP Error 401: Invalid Crumb").
                # Treat these as provider-wide failures too, or each caller retries.
                if any(
                    token in message
                    for token in (
                        "429", "401", "403", "rate-limit", "rate limit",
                        "rate limited", "too many requests", "unauthorized",
                        "invalid crumb", "unable to access this feature",
                    )
                ):
                    self.rate_limited = True

        yfinance_logger = logging.getLogger("yfinance")
        crumb_capture = _CrumbRateLimitCapture(level=logging.WARNING)
        yfinance_logger.addHandler(crumb_capture)
        try:
            history_kwargs = {}
            if start is not None:
                history_kwargs["start"] = start
                if end is not None:
                    history_kwargs["end"] = end
            elif period:
                history_kwargs["period"] = period
            if interval:
                history_kwargs["interval"] = interval
            data = yf.Ticker(ticker).history(**history_kwargs)
        except Exception as exc:
            message = str(exc).lower()
            rate_limited = any(
                token in message
                for token in ("429", "401", "403", "crumb", "rate limit", "too many requests")
            )
            if rate_limited:
                _YFINANCE_COOLDOWN_UNTIL = time.monotonic() + _YFINANCE_RATE_LIMIT_SECONDS
                _YFINANCE_COOLDOWN_REASON = "rate/auth limit"
                _YFINANCE_COOLDOWN_LOGGED = False
                logger.warning(
                    "Yahoo Finance history rate/auth failure for %s; cooling down globally for %ss",
                    ticker, _YFINANCE_RATE_LIMIT_SECONDS,
                )
            else:
                _set_yfinance_symbol_cooldown(ticker)
                logger.warning(
                    "Yahoo Finance history failed for %s (%s); cooling down this symbol for %ss",
                    ticker, type(exc).__name__, _YFINANCE_SYMBOL_COOLDOWN_SECONDS,
                )
            return None
        finally:
            yfinance_logger.removeHandler(crumb_capture)

        if crumb_capture.rate_limited:
            _YFINANCE_COOLDOWN_UNTIL = time.monotonic() + _YFINANCE_RATE_LIMIT_SECONDS
            _YFINANCE_COOLDOWN_REASON = "crumb rate limit"
            _YFINANCE_COOLDOWN_LOGGED = False
            logger.warning(
                "Yahoo Finance crumb rate limit detected for %s; cooling down for %ss",
                ticker, _YFINANCE_RATE_LIMIT_SECONDS,
            )
            return None

        if data is None or data.empty:
            _set_yfinance_symbol_cooldown(ticker)
            logger.warning(
                "Yahoo Finance returned empty history for %s; cooling down this symbol for %ss",
                ticker, _YFINANCE_SYMBOL_COOLDOWN_SECONDS,
            )
            return None

        _YFINANCE_SYMBOL_COOLDOWNS.pop(ticker, None)
        _YFINANCE_COOLDOWN_UNTIL = 0.0
        _YFINANCE_COOLDOWN_REASON = ""
        _YFINANCE_COOLDOWN_LOGGED = False
        return data


def _fetch_yfinance_info(ticker: str) -> dict | None:
    """Fetch Yahoo metadata under the same process-wide lock and cooldown."""
    global _YFINANCE_COOLDOWN_UNTIL, _YFINANCE_COOLDOWN_REASON
    global _YFINANCE_COOLDOWN_LOGGED

    import yfinance as yf

    with _YFINANCE_LOCK:
        now = time.monotonic()
        if now < _YFINANCE_COOLDOWN_UNTIL:
            if not _YFINANCE_COOLDOWN_LOGGED:
                logger.warning(
                    "Yahoo Finance requests paused for %.0fs after provider failure (%s)",
                    _YFINANCE_COOLDOWN_UNTIL - now,
                    _YFINANCE_COOLDOWN_REASON or "unavailable data",
                )
                _YFINANCE_COOLDOWN_LOGGED = True
            return None

        class _AuthFailureCapture(logging.Handler):
            failed = False

            def emit(self, record):
                message = record.getMessage().lower()
                if any(token in message for token in (
                    "429", "401", "403", "rate-limit", "rate limit",
                    "rate limited", "too many requests", "unauthorized",
                    "invalid crumb", "unable to access this feature",
                )):
                    self.failed = True

        yfinance_logger = logging.getLogger("yfinance")
        capture = _AuthFailureCapture(level=logging.WARNING)
        yfinance_logger.addHandler(capture)
        try:
            info = yf.Ticker(ticker).info
        except Exception as exc:
            message = str(exc).lower()
            rate_limited = any(token in message for token in (
                "429", "401", "403", "crumb", "rate limit", "too many requests"
            ))
            cooldown = _YFINANCE_RATE_LIMIT_SECONDS if rate_limited else _YFINANCE_COOLDOWN_SECONDS
            _YFINANCE_COOLDOWN_UNTIL = time.monotonic() + cooldown
            _YFINANCE_COOLDOWN_REASON = "rate/auth limit" if rate_limited else type(exc).__name__
            _YFINANCE_COOLDOWN_LOGGED = False
            logger.warning(
                "Yahoo Finance metadata failed for %s (%s); cooling down for %ss",
                ticker, _YFINANCE_COOLDOWN_REASON, cooldown,
            )
            return None
        finally:
            yfinance_logger.removeHandler(capture)

        if capture.failed:
            _YFINANCE_COOLDOWN_UNTIL = time.monotonic() + _YFINANCE_RATE_LIMIT_SECONDS
            _YFINANCE_COOLDOWN_REASON = "metadata auth/rate limit"
            _YFINANCE_COOLDOWN_LOGGED = False
            logger.warning(
                "Yahoo Finance metadata rate/auth failure for %s; cooling down for %ss",
                ticker, _YFINANCE_RATE_LIMIT_SECONDS,
            )
            return None

        if not isinstance(info, dict) or not info:
            return None
        _YFINANCE_COOLDOWN_UNTIL = 0.0
        _YFINANCE_COOLDOWN_REASON = ""
        _YFINANCE_COOLDOWN_LOGGED = False
        return info


def _fetch_yfinance_earnings_dates(ticker: str, limit: int = 8):
    """Fetch earnings dates under the same Yahoo lock and provider cooldown."""
    global _YFINANCE_COOLDOWN_UNTIL, _YFINANCE_COOLDOWN_REASON
    global _YFINANCE_COOLDOWN_LOGGED

    import yfinance as yf

    with _YFINANCE_LOCK:
        now = time.monotonic()
        if now < _YFINANCE_COOLDOWN_UNTIL:
            if not _YFINANCE_COOLDOWN_LOGGED:
                logger.warning(
                    "Yahoo Finance requests paused for %.0fs after provider failure (%s)",
                    _YFINANCE_COOLDOWN_UNTIL - now,
                    _YFINANCE_COOLDOWN_REASON or "unavailable data",
                )
                _YFINANCE_COOLDOWN_LOGGED = True
            return None

        class _AuthFailureCapture(logging.Handler):
            failed = False

            def emit(self, record):
                message = record.getMessage().lower()
                if any(token in message for token in (
                    "429", "401", "403", "rate-limit", "rate limit",
                    "rate limited", "too many requests", "unauthorized",
                    "invalid crumb", "unable to access this feature",
                )):
                    self.failed = True

        yfinance_logger = logging.getLogger("yfinance")
        capture = _AuthFailureCapture(level=logging.WARNING)
        yfinance_logger.addHandler(capture)
        try:
            data = yf.Ticker(ticker).get_earnings_dates(limit=limit)
        except Exception as exc:
            message = str(exc).lower()
            rate_limited = any(token in message for token in (
                "429", "401", "403", "crumb", "rate limit", "too many requests"
            ))
            cooldown = _YFINANCE_RATE_LIMIT_SECONDS if rate_limited else _YFINANCE_COOLDOWN_SECONDS
            _YFINANCE_COOLDOWN_UNTIL = time.monotonic() + cooldown
            _YFINANCE_COOLDOWN_REASON = "rate/auth limit" if rate_limited else type(exc).__name__
            _YFINANCE_COOLDOWN_LOGGED = False
            logger.warning(
                "Yahoo Finance earnings dates failed for %s (%s); cooling down for %ss",
                ticker, _YFINANCE_COOLDOWN_REASON, cooldown,
            )
            return None
        finally:
            yfinance_logger.removeHandler(capture)

        if capture.failed:
            _YFINANCE_COOLDOWN_UNTIL = time.monotonic() + _YFINANCE_RATE_LIMIT_SECONDS
            _YFINANCE_COOLDOWN_REASON = "earnings metadata auth/rate limit"
            _YFINANCE_COOLDOWN_LOGGED = False
            logger.warning(
                "Yahoo Finance earnings auth/rate failure for %s; cooling down for %ss",
                ticker, _YFINANCE_RATE_LIMIT_SECONDS,
            )
            return None

        _YFINANCE_COOLDOWN_UNTIL = 0.0
        _YFINANCE_COOLDOWN_REASON = ""
        _YFINANCE_COOLDOWN_LOGGED = False
        return data


def _fetch_yfinance_news(ticker: str):
    """Fetch ticker news under the shared Yahoo lock and cooldown."""
    global _YFINANCE_COOLDOWN_UNTIL, _YFINANCE_COOLDOWN_REASON
    global _YFINANCE_COOLDOWN_LOGGED

    import yfinance as yf

    with _YFINANCE_LOCK:
        now = time.monotonic()
        if now < _YFINANCE_COOLDOWN_UNTIL:
            if not _YFINANCE_COOLDOWN_LOGGED:
                logger.warning(
                    "Yahoo Finance requests paused for %.0fs after provider failure (%s)",
                    _YFINANCE_COOLDOWN_UNTIL - now,
                    _YFINANCE_COOLDOWN_REASON or "unavailable data",
                )
                _YFINANCE_COOLDOWN_LOGGED = True
            return None

        class _AuthFailureCapture(logging.Handler):
            failed = False

            def emit(self, record):
                message = record.getMessage().lower()
                if any(token in message for token in (
                    "429", "401", "403", "rate-limit", "rate limit",
                    "rate limited", "too many requests", "unauthorized",
                    "invalid crumb", "unable to access this feature",
                )):
                    self.failed = True

        yfinance_logger = logging.getLogger("yfinance")
        capture = _AuthFailureCapture(level=logging.WARNING)
        yfinance_logger.addHandler(capture)
        try:
            news = yf.Ticker(ticker).news
        except Exception as exc:
            message = str(exc).lower()
            rate_limited = any(token in message for token in (
                "429", "401", "403", "crumb", "rate limit", "too many requests"
            ))
            cooldown = _YFINANCE_RATE_LIMIT_SECONDS if rate_limited else _YFINANCE_COOLDOWN_SECONDS
            _YFINANCE_COOLDOWN_UNTIL = time.monotonic() + cooldown
            _YFINANCE_COOLDOWN_REASON = "rate/auth limit" if rate_limited else type(exc).__name__
            _YFINANCE_COOLDOWN_LOGGED = False
            logger.warning(
                "Yahoo Finance news failed for %s (%s); cooling down for %ss",
                ticker, _YFINANCE_COOLDOWN_REASON, cooldown,
            )
            return None
        finally:
            yfinance_logger.removeHandler(capture)

        if capture.failed:
            _YFINANCE_COOLDOWN_UNTIL = time.monotonic() + _YFINANCE_RATE_LIMIT_SECONDS
            _YFINANCE_COOLDOWN_REASON = "news auth/rate limit"
            _YFINANCE_COOLDOWN_LOGGED = False
            logger.warning(
                "Yahoo Finance news auth/rate failure for %s; cooling down for %ss",
                ticker, _YFINANCE_RATE_LIMIT_SECONDS,
            )
            return None

        _YFINANCE_COOLDOWN_UNTIL = 0.0
        _YFINANCE_COOLDOWN_REASON = ""
        _YFINANCE_COOLDOWN_LOGGED = False
        return news

def get_current_price(ticker_raw: str) -> float | None:
    """Текущая цена актива — для трек-рекорда рекомендаций."""
    ticker = resolve_ticker(ticker_raw)
    if not ticker:
        return None
    try:
        data = _fetch_yfinance_history(ticker, period="1d")
        if data is None or "Close" not in data.columns or data["Close"].dropna().empty:
            return None
        return float(data["Close"].iloc[-1])
    except Exception as e:
        logger.error(f"get_current_price error ({ticker}): {e}")
        return None


def get_price_metrics(
    ticker_raw: str,
    entry_price: float,
    entry_time: str | None = None,
    recommendation: str = "long",
) -> dict | None:
    """Return PnL and adverse price movement only since a signal was posted."""
    from datetime import datetime, timezone

    ticker = resolve_ticker(ticker_raw)
    if not ticker or not entry_price:
        return None
    try:
        # Signals are checked after horizons of at most several days. One month
        # of hourly candles covers the period while avoiding a year of unrelated
        # price history in the drawdown calculation.
        data = _fetch_yfinance_history(ticker, period="1mo", interval="1h")
        if data is None or data.empty or "Close" not in data.columns:
            return None

        if entry_time:
            start = datetime.fromisoformat(str(entry_time).replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if data.index.tz is None:
                data.index = data.index.tz_localize("UTC")
            else:
                data.index = data.index.tz_convert("UTC")
            data = data[data.index >= start.astimezone(timezone.utc)]
        if data.empty:
            logger.warning("get_price_metrics: no candles since signal entry for %s", ticker)
            return None

        closes = data["Close"].dropna()
        if closes.empty:
            return None
        current = float(closes.iloc[-1])
        lows = data["Low"] if "Low" in data.columns else data["Close"]
        highs = data["High"] if "High" in data.columns else data["Close"]
        if str(recommendation).lower() == "short":
            # Negative values represent adverse movement for either direction.
            adverse_moves = [(entry_price - float(value)) / entry_price * 100
                             for value in highs.dropna().tolist()]
        else:
            adverse_moves = [(float(value) - entry_price) / entry_price * 100
                             for value in lows.dropna().tolist()]
        max_adverse = min([0.0, *adverse_moves])
        return {
            "price_after": current,
            "pnl_percent": (current - entry_price) / entry_price * 100,
            "max_drawdown_percent": max_adverse,
        }
    except Exception as exc:
        logger.error("get_price_metrics error (%s): %s", ticker, exc)
        return None


def get_sparkline_data(ticker_raw: str, period: str = "5d") -> dict | None:
    """Данные для мини-графика (sparkline) через общий Yahoo cooldown."""
    ticker = resolve_ticker(ticker_raw)
    if not ticker:
        return None
    try:
        # Route this request through the same cooldown used by price tracking.
        # yf.download() bypasses the shared guard and can keep hitting Yahoo
        # while its crumb endpoint is rate-limited.
        data = _fetch_yfinance_history(ticker, period=period, interval="1h")
        if data is None or data.empty:
            return None
        close = data["Close"] if "Close" in data.columns else data.iloc[:, 0]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        close = close.dropna()
        if len(close) < 2:
            return None
        values = [float(v) for v in close.values]
        pct = (values[-1] - values[0]) / values[0] * 100
        return {"ticker": ticker, "values": values, "last": values[-1], "change_pct": pct}
    except Exception as e:
        logger.error(f"get_sparkline_data error ({ticker}): {e}")
        return None

def build_chart(ticker_raw: str) -> bytes | None:
    ticker = resolve_ticker(ticker_raw)
    if not ticker:
        return None

    # 1. Chart-IMG API, if its optional key is already configured.
    result = _chart_img(ticker)
    if result:
        return result

    # 2. Finviz — validates image size and rejects placeholder charts.
    result = _finviz_chart(ticker)
    if result:
        return result

    # 3. yfinance + matplotlib can push Render's 512 MiB free instance over
    # its memory limit. In production, let the caller use its photo fallback
    # instead of risking an OOM restart; retain chart generation for local use.
    if os.getenv("RENDER_SERVICE_ID"):
        logger.warning(
            "Skipping matplotlib chart fallback for %s on Render to protect memory",
            ticker,
        )
        return None

    logger.info("Finviz failed or returned placeholder for %s; using yfinance fallback", ticker)
    return _yfinance_chart(ticker)
