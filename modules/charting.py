import io
import time
import logging
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import yfinance as yf

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
    """Fallback: свой график в стиле Apple Stocks —
    тёмный фон, крупная цена/% сверху, тонкая area-заливка под линией."""
    sparkline = get_sparkline_data(ticker, period)
    if not sparkline:
        return None

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
        logger.error(f"yfinance Apple-style chart error ({ticker}): {e}")
        return None


def get_current_price(ticker_raw: str) -> float | None:
    """Текущая цена актива — для трек-рекорда рекомендаций."""
    ticker = resolve_ticker(ticker_raw)
    if not ticker:
        return None
    try:
        data = yf.Ticker(ticker).history(period="1d")
        if data.empty:
            return None
        return float(data["Close"].iloc[-1])
    except Exception as e:
        logger.error(f"get_current_price error ({ticker}): {e}")
        return None


def get_sparkline_data(ticker_raw: str, period: str = "5d") -> dict | None:
    """Данные для мини-графика (sparkline) в Apple-стиле."""
    ticker = resolve_ticker(ticker_raw)
    if not ticker:
        return None
    try:
        data = yf.download(
            ticker, period=period, interval="1h",
            progress=False, auto_adjust=True, multi_level_index=False
        )
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

    # 1. Try Finviz (primary) — проверяет размер и отбрасывает заглушки
    result = _finviz_chart(ticker)
    if result:
        return result

    # 2. Fallback: yfinance + matplotlib
    logger.info(f"Finviz failed or returned placeholder for {ticker}, using yfinance fallback")
    return _yfinance_chart(ticker)
