import io
import time
import logging
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
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


def resolve_ticker(raw: str) -> str | None:
    if not raw:
        return None
    lower = raw.lower().strip()
    if lower in TICKER_ALIASES:
        return TICKER_ALIASES[lower]
    return raw.upper()


def _finviz_chart(ticker: str) -> bytes | None:
    """Fetch chart from Finviz with proper browser headers. 2 attempts."""
    finviz_ticker = FINVIZ_TICKER_MAP.get(ticker, ticker)
    if finviz_ticker is None:
        return None

    url = f"https://finviz.com/chart.ashx?t={finviz_ticker}&ty=c&ta=1&p=d&s=l"
    for attempt in range(2):
        try:
            r = requests.get(url, headers=FINVIZ_HEADERS, timeout=10)
            ct = r.headers.get("Content-Type", "")
            if r.status_code == 200 and ct.startswith("image/"):
                logger.info(f"Finviz chart OK for {finviz_ticker}")
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
    """Fallback: light-theme chart via yfinance + matplotlib."""
    try:
        data = yf.download(
            ticker, period=period, interval="1h",
            progress=False, auto_adjust=True, multi_level_index=False
        )
        if data is None or data.empty or len(data) < 5:
            logger.warning(f"yfinance: no data for {ticker}")
            return None

        close = data["Close"] if "Close" in data.columns else data.iloc[:, 0]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        close = close.dropna()
        if len(close) < 5:
            return None

        fig, ax = plt.subplots(figsize=(10, 5))
        fig.patch.set_facecolor("white")
        ax.set_facecolor("#f8f9fa")

        is_up = close.iloc[-1] >= close.iloc[0]
        color = "#16a34a" if is_up else "#dc2626"
        ax.plot(close.index, close.values, color=color, linewidth=2)
        ax.fill_between(close.index, close.values, alpha=0.08, color=color)

        pct = (close.iloc[-1] - close.iloc[0]) / close.iloc[0] * 100
        sign = "+" if pct >= 0 else ""
        ax.set_title(f"{ticker}   {sign}{pct:.2f}%", color="#111111",
                     fontsize=14, fontweight="bold", pad=12)
        ax.tick_params(colors="#444444", labelsize=9)
        for spine in ax.spines.values():
            spine.set_color("#cccccc")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m %H:%M"))
        plt.xticks(rotation=25, ha='right', color="#444444")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.2f}"))
        ax.grid(True, color="#e5e7eb", linestyle="--", linewidth=0.6)
        fig.text(0.99, 0.01, "TRIADA INVESTING", ha="right", va="bottom",
                 fontsize=8, color="#aaaaaa")
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
        buf.seek(0)
        plt.close(fig)
        return buf.getvalue()

    except Exception as e:
        logger.error(f"yfinance chart error ({ticker}): {e}")
        return None


def get_current_price(ticker_raw: str) -> float | None:
    """Текущая цена актива — для трек-рекорда рекомендаций (сверка через 24ч).
    Переиспользует resolve_ticker и yfinance, уже используемые для графиков —
    отдельной зависимости не требуется."""
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


def build_chart(ticker_raw: str) -> bytes | None:
    ticker = resolve_ticker(ticker_raw)
    if not ticker:
        return None

    # 1. Try Finviz (primary)
    result = _finviz_chart(ticker)
    if result:
        return result

    # 2. Fallback: yfinance + matplotlib
    logger.info(f"Finviz failed for {ticker}, using yfinance fallback")
    return _yfinance_chart(ticker)
