"""Smart alerts - advanced alert types beyond simple price alerts.

Alert types:
- breakout: price breaks above resistance level
- breakdown: price breaks below support level
- rsi_oversold: RSI < 30
- rsi_overbought: RSI > 70
- volume_spike: volume > 2x average
- golden_cross: 50 SMA crosses above 200 SMA
- death_cross: 50 SMA crosses below 200 SMA
"""
import asyncio
import logging
from typing import Any

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)


async def check_breakout(ticker: str, resistance: float) -> dict[str, Any] | None:
    """Check if price broke above resistance level."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        hist = await asyncio.to_thread(lambda: stock.history(period="5d"))

        if hist.empty or len(hist) < 2:
            return None

        current_price = hist["Close"].iloc[-1]
        prev_price = hist["Close"].iloc[-2]

        # Breakout = prev below resistance, current above resistance
        if prev_price <= resistance and current_price > resistance:
            return {
                "triggered": True,
                "type": "breakout",
                "ticker": ticker,
                "current_price": current_price,
                "level": resistance,
                "message": f"🚀 <b>{ticker}</b> пробил сопротивление ${resistance:.2f}\nТекущая цена: ${current_price:.2f}",
            }

        return None
    except Exception as e:
        logger.error(f"Error checking breakout for {ticker}: {e}")
        return None


async def check_breakdown(ticker: str, support: float) -> dict[str, Any] | None:
    """Check if price broke below support level."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        hist = await asyncio.to_thread(lambda: stock.history(period="5d"))

        if hist.empty or len(hist) < 2:
            return None

        current_price = hist["Close"].iloc[-1]
        prev_price = hist["Close"].iloc[-2]

        # Breakdown = prev above support, current below support
        if prev_price >= support and current_price < support:
            return {
                "triggered": True,
                "type": "breakdown",
                "ticker": ticker,
                "current_price": current_price,
                "level": support,
                "message": f"📉 <b>{ticker}</b> пробил поддержку ${support:.2f}\nТекущая цена: ${current_price:.2f}",
            }

        return None
    except Exception as e:
        logger.error(f"Error checking breakdown for {ticker}: {e}")
        return None


async def check_rsi_oversold(ticker: str, threshold: float = 30) -> dict[str, Any] | None:
    """Check if RSI is oversold (< threshold)."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        hist = await asyncio.to_thread(lambda: stock.history(period="3mo"))

        if hist.empty or len(hist) < 14:
            return None

        # Calculate RSI
        close = hist["Close"]
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        current_rsi = rsi.iloc[-1]
        current_price = close.iloc[-1]

        if current_rsi < threshold:
            return {
                "triggered": True,
                "type": "rsi_oversold",
                "ticker": ticker,
                "current_price": current_price,
                "rsi": current_rsi,
                "message": f"📊 <b>{ticker}</b> перепродан (RSI {current_rsi:.1f})\nТекущая цена: ${current_price:.2f}",
            }

        return None
    except Exception as e:
        logger.error(f"Error checking RSI for {ticker}: {e}")
        return None


async def check_rsi_overbought(ticker: str, threshold: float = 70) -> dict[str, Any] | None:
    """Check if RSI is overbought (> threshold)."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        hist = await asyncio.to_thread(lambda: stock.history(period="3mo"))

        if hist.empty or len(hist) < 14:
            return None

        # Calculate RSI
        close = hist["Close"]
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        current_rsi = rsi.iloc[-1]
        current_price = close.iloc[-1]

        if current_rsi > threshold:
            return {
                "triggered": True,
                "type": "rsi_overbought",
                "ticker": ticker,
                "current_price": current_price,
                "rsi": current_rsi,
                "message": f"📊 <b>{ticker}</b> перекуплен (RSI {current_rsi:.1f})\nТекущая цена: ${current_price:.2f}",
            }

        return None
    except Exception as e:
        logger.error(f"Error checking RSI for {ticker}: {e}")
        return None


async def check_volume_spike(ticker: str, multiplier: float = 2.0) -> dict[str, Any] | None:
    """Check if current volume is X times higher than average."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        hist = await asyncio.to_thread(lambda: stock.history(period="1mo"))

        if hist.empty or len(hist) < 20:
            return None

        current_volume = hist["Volume"].iloc[-1]
        avg_volume = hist["Volume"].iloc[-20:-1].mean()

        if current_volume > avg_volume * multiplier:
            current_price = hist["Close"].iloc[-1]
            ratio = current_volume / avg_volume

            return {
                "triggered": True,
                "type": "volume_spike",
                "ticker": ticker,
                "current_price": current_price,
                "volume_ratio": ratio,
                "message": f"💥 <b>{ticker}</b> аномальный объем ({ratio:.1f}x средний)\nТекущая цена: ${current_price:.2f}",
            }

        return None
    except Exception as e:
        logger.error(f"Error checking volume for {ticker}: {e}")
        return None


async def check_golden_cross(ticker: str) -> dict[str, Any] | None:
    """Check if 50 SMA crossed above 200 SMA (bullish signal)."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        hist = await asyncio.to_thread(lambda: stock.history(period="1y"))

        if hist.empty or len(hist) < 200:
            return None

        close = hist["Close"]
        sma_50 = close.rolling(window=50).mean()
        sma_200 = close.rolling(window=200).mean()

        # Golden cross = 50 SMA crosses above 200 SMA
        prev_50 = sma_50.iloc[-2]
        prev_200 = sma_200.iloc[-2]
        current_50 = sma_50.iloc[-1]
        current_200 = sma_200.iloc[-1]

        if prev_50 <= prev_200 and current_50 > current_200:
            current_price = close.iloc[-1]

            return {
                "triggered": True,
                "type": "golden_cross",
                "ticker": ticker,
                "current_price": current_price,
                "sma_50": current_50,
                "sma_200": current_200,
                "message": f"✨ <b>{ticker}</b> Golden Cross (50 SMA > 200 SMA)\nТекущая цена: ${current_price:.2f}",
            }

        return None
    except Exception as e:
        logger.error(f"Error checking golden cross for {ticker}: {e}")
        return None


async def check_death_cross(ticker: str) -> dict[str, Any] | None:
    """Check if 50 SMA crossed below 200 SMA (bearish signal)."""
    try:
        stock = await asyncio.to_thread(yf.Ticker, ticker)
        hist = await asyncio.to_thread(lambda: stock.history(period="1y"))

        if hist.empty or len(hist) < 200:
            return None

        close = hist["Close"]
        sma_50 = close.rolling(window=50).mean()
        sma_200 = close.rolling(window=200).mean()

        # Death cross = 50 SMA crosses below 200 SMA
        prev_50 = sma_50.iloc[-2]
        prev_200 = sma_200.iloc[-2]
        current_50 = sma_50.iloc[-1]
        current_200 = sma_200.iloc[-1]

        if prev_50 >= prev_200 and current_50 < current_200:
            current_price = close.iloc[-1]

            return {
                "triggered": True,
                "type": "death_cross",
                "ticker": ticker,
                "current_price": current_price,
                "sma_50": current_50,
                "sma_200": current_200,
                "message": f"💀 <b>{ticker}</b> Death Cross (50 SMA < 200 SMA)\nТекущая цена: ${current_price:.2f}",
            }

        return None
    except Exception as e:
        logger.error(f"Error checking death cross for {ticker}: {e}")
        return None


async def check_smart_alert(alert_type: str, ticker: str, params: dict = None) -> dict[str, Any] | None:
    """Check a smart alert based on type."""
    params = params or {}

    if alert_type == "breakout":
        return await check_breakout(ticker, params.get("level", 0))
    elif alert_type == "breakdown":
        return await check_breakdown(ticker, params.get("level", 0))
    elif alert_type == "rsi_oversold":
        return await check_rsi_oversold(ticker, params.get("threshold", 30))
    elif alert_type == "rsi_overbought":
        return await check_rsi_overbought(ticker, params.get("threshold", 70))
    elif alert_type == "volume_spike":
        return await check_volume_spike(ticker, params.get("multiplier", 2.0))
    elif alert_type == "golden_cross":
        return await check_golden_cross(ticker)
    elif alert_type == "death_cross":
        return await check_death_cross(ticker)
    else:
        logger.warning(f"Unknown smart alert type: {alert_type}")
        return None
