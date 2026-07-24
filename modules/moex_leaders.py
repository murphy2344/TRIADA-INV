"""
    Лидеры роста/падения международного рынка (S&P 500 / NASDAQ) — через yfinance.
    Максимум 1 российская компания в выборке (Сбербанк ADR).
    """
    import logging
    import concurrent.futures
    import yfinance as yf

    logger = logging.getLogger(__name__)

    # Международные blue chips (S&P 500 / NASDAQ) + 1 российская ADR
    TICKERS = [
      # Tech
      "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
      "AMD", "INTC", "NFLX", "ADBE", "CRM", "AVGO",
      # Finance
      "JPM", "GS", "MS", "BAC", "C", "V", "MA",
      # Health / Consumer
      "JNJ", "UNH", "LLY", "ABBV", "MRK", "PEP", "KO", "WMT", "PG",
      "COST", "MCD", "HD",
      # Energy / Industry
      "XOM", "CVX", "BA", "TMO",
      # Russian ADR (представитель РФ — максимум 1 компания попадёт в топ)
      "SBRCY",
    ]

    DISPLAY_NAMES = {
      "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA",
      "GOOGL": "Alphabet", "AMZN": "Amazon", "META": "Meta",
      "TSLA": "Tesla", "AMD": "AMD", "INTC": "Intel",
      "NFLX": "Netflix", "ADBE": "Adobe", "CRM": "Salesforce", "AVGO": "Broadcom",
      "JPM": "JPMorgan", "GS": "Goldman Sachs", "MS": "Morgan Stanley",
      "BAC": "Bank of America", "C": "Citigroup", "V": "Visa", "MA": "Mastercard",
      "JNJ": "Johnson & Johnson", "UNH": "UnitedHealth", "LLY": "Eli Lilly",
      "ABBV": "AbbVie", "MRK": "Merck", "PEP": "PepsiCo", "KO": "Coca-Cola",
      "WMT": "Walmart", "PG": "Procter & Gamble", "COST": "Costco",
      "MCD": "McDonald's", "HD": "Home Depot",
      "XOM": "Exxon Mobil", "CVX": "Chevron", "BA": "Boeing", "TMO": "Thermo Fisher",
      "SBRCY": "Сбербанк ADR",
    }


    def _get_change(ticker: str) -> dict | None:
      try:
          hist = yf.Ticker(ticker).history(period="5d", interval="1d")
          if hist is None or len(hist) < 2:
              return None
          prev_close = float(hist["Close"].iloc[-2])
          last = float(hist["Close"].iloc[-1])
          if prev_close == 0:
              return None
          change_pct = (last - prev_close) / prev_close * 100
          return {
              "ticker": ticker,
              "name": DISPLAY_NAMES.get(ticker, ticker),
              "last": round(last, 2),
              "change_pct": round(change_pct, 2),
          }
      except Exception as e:
          logger.error(f"yfinance error ({ticker}): {e}")
          return None


    def get_leaders(top_n: int = 5) -> dict:
      """Возвращает {"gainers": [...], "losers": [...]}.
      Каждый элемент: {ticker, name, last, change_pct}"""
      results = []
      with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
          futures = [ex.submit(_get_change, t) for t in TICKERS]
          for f in concurrent.futures.as_completed(futures):
              res = f.result()
              if res is not None:
                  results.append(res)

      results.sort(key=lambda x: x["change_pct"], reverse=True)
      gainers = [r for r in results if r["change_pct"] > 0][:top_n]
      losers = list(reversed([r for r in results if r["change_pct"] < 0]))[:top_n]
      return {"gainers": gainers, "losers": losers}


    def get_all_periods_leaders(top_n: int = 5) -> dict:
      """Обёртка для обратной совместимости с pipeline/formatter.
      Возвращает {"day": (gainers, losers)} — формат, который ожидает fmt_leaders."""
      data = get_leaders(top_n)
      return {"day": (data["gainers"], data["losers"])}
    