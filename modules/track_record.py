"""Signal horizons and metrics used by the recommendation track record."""

HORIZONS = {
    "macro": 72,
    "earnings": 24,
    "geopolitics": 48,
    "corporate": 48,
    "central_bank": 120,
    "commodity": 72,
    "regulatory": 48,
    "bonds": 72,
    "market_move": 24,
    "company": 48,
}


def horizon_for(category: str | None) -> int:
    return HORIZONS.get(category or "market_move", 24)