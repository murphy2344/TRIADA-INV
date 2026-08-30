"""
COT (Commitments of Traders) — позиции крупных игроков.

Источник: официальный Socrata API от CFTC (регулятор США), без ключа.
Датасет "Legacy — Combined" (фьючерсы+опционы):
GET https://publicreporting.cftc.gov/resource/jun7-fc8e.json

Поля подтверждены тестовым запросом к API:
- market_and_exchange_names — название контракта
- report_date_as_yyyy_mm_dd — дата отчёта
- noncomm_positions_long_all — крупные спекулянты, лонг
- noncomm_positions_short_all — крупные спекулянты, шорт
- comm_positions_long_all — коммерческие хеджеры, лонг
- comm_positions_short_all — коммерческие хеджеры, шорт
"""
import logging
import requests

logger = logging.getLogger(__name__)

CFTC_URL = "https://publicreporting.cftc.gov/resource/jun7-fc8e.json"
TIMEOUT = 15

# Сопоставление наших тикеров с подстрокой для поиска в market_and_exchange_names CFTC
# Подстрока должна однозначно идентифицировать нужный контракт (проверено)
WATCHLIST_COT = {
    "GC=F":  "GOLD",
    "CL=F":  "CRUDE OIL",
    "6E=F":  "EURO FX",
    "6J=F":  "JAPANESE YEN",
    "ES=F":  "S&P 500",
}


def fetch_cot(contract_keyword: str) -> dict | None:
    """Последний COT-отчёт по контракту (по ключевому слову в названии).
    Возвращает словарь с позициями или None при ошибке."""
    try:
        params = {
            "$where": f"market_and_exchange_names like '%{contract_keyword}%'",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": "1",
        }
        resp = requests.get(CFTC_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            logger.warning(f"COT: no data for '{contract_keyword}'")
            return None

        row = data[0]
        return {
            "contract": row.get("market_and_exchange_names", contract_keyword),
            "date": row.get("report_date_as_yyyy_mm_dd", "")[:10],
            "large_spec_long":  int(row.get("noncomm_positions_long_all", 0) or 0),
            "large_spec_short": int(row.get("noncomm_positions_short_all", 0) or 0),
            "commercial_long":  int(row.get("comm_positions_long_all", 0) or 0),
            "commercial_short": int(row.get("comm_positions_short_all", 0) or 0),
        }
    except Exception as e:
        logger.error(f"COT fetch error for '{contract_keyword}': {e}")
        return None


def fetch_all_cot() -> list[dict]:
    """Загружает COT по всем контрактам из WATCHLIST_COT.
    Один сбойный контракт не роняет остальные — как в earnings.py."""
    results = []
    for ticker, keyword in WATCHLIST_COT.items():
        try:
            item = fetch_cot(keyword)
            if item:
                item["ticker"] = ticker
                results.append(item)
        except Exception as e:
            logger.error(f"fetch_all_cot: skip {ticker} due to error: {e}")
            continue
    return results
