"""WebSocket real-time price feed for crypto via ccxt pro or manual WS."""

import threading
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# In-memory latest prices (thread-safe via GIL for simple reads/writes)
_latest_prices: dict[str, dict] = {}
_ws_thread = None
_running = False


def get_live_price(symbol: str) -> dict | None:
    """Get the latest cached price from the WebSocket feed."""
    return _latest_prices.get(symbol)


def get_all_live_prices() -> dict[str, dict]:
    """Get all cached live prices."""
    return dict(_latest_prices)


def _ws_polling_loop(symbols: list[str], interval: float = 10.0):
    """Fallback polling loop using REST when WebSocket is not available.

    Polls every `interval` seconds for each symbol.
    """
    global _running
    from data.crypto_fetcher import get_crypto_price

    while _running:
        for sym in symbols:
            if not _running:
                break
            try:
                data = get_crypto_price(sym)
                if data:
                    _latest_prices[sym] = {
                        **data,
                        "updated_at": datetime.now().isoformat(),
                    }
            except Exception as e:
                logger.debug("WS poll error for %s: %s", sym, e)
        # Sleep in small chunks for responsive shutdown
        for _ in range(int(interval)):
            if not _running:
                break
            time.sleep(1)


def _ws_okx_loop(symbols: list[str]):
    """Connect to OKX WebSocket for real-time tickers."""
    global _running

    try:
        import websockets
        import asyncio
        import json
    except ImportError:
        logger.info("websockets not installed, falling back to polling")
        _ws_polling_loop(symbols)
        return

    # Convert symbols to OKX format: BTC/USDT → BTC-USDT
    okx_symbols = [s.replace("/", "-") for s in symbols]

    async def _connect():
        uri = "wss://ws.okx.com:8443/ws/v5/public"
        while _running:
            try:
                async with websockets.connect(uri, ping_interval=20) as ws:
                    # Subscribe to tickers
                    sub_msg = {
                        "op": "subscribe",
                        "args": [{"channel": "tickers", "instId": s} for s in okx_symbols]
                    }
                    await ws.send(json.dumps(sub_msg))
                    logger.info("WebSocket connected to OKX for %d symbols", len(symbols))

                    async for message in ws:
                        if not _running:
                            break
                        try:
                            data = json.loads(message)
                            if "data" in data and data.get("arg", {}).get("channel") == "tickers":
                                for tick in data["data"]:
                                    inst_id = tick.get("instId", "")
                                    # Convert back: BTC-USDT → BTC/USDT
                                    symbol = inst_id.replace("-", "/")
                                    last = float(tick.get("last", 0))
                                    open24h = float(tick.get("open24h", 0))
                                    change = last - open24h
                                    change_pct = (change / open24h * 100) if open24h else 0

                                    _latest_prices[symbol] = {
                                        "symbol": symbol,
                                        "price": round(last, 2),
                                        "change": round(change, 2),
                                        "change_pct": round(change_pct, 2),
                                        "high_24h": float(tick.get("high24h", 0)),
                                        "low_24h": float(tick.get("low24h", 0)),
                                        "volume_24h": float(tick.get("volCcy24h", 0)),
                                        "updated_at": datetime.now().isoformat(),
                                    }
                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue
            except Exception as e:
                logger.warning("WebSocket disconnected: %s, reconnecting in 5s", e)
                await asyncio.sleep(5)

    try:
        asyncio.run(_connect())
    except Exception as e:
        logger.warning("WebSocket loop failed: %s, falling back to polling", e)
        _ws_polling_loop(symbols)


def start_price_feed(symbols: list[str] = None, use_websocket: bool = True):
    """Start the real-time price feed in a background thread."""
    global _ws_thread, _running

    if _running:
        return

    if symbols is None:
        from config import DEFAULT_CRYPTO
        symbols = DEFAULT_CRYPTO

    _running = True
    target = _ws_okx_loop if use_websocket else _ws_polling_loop
    _ws_thread = threading.Thread(
        target=target,
        args=(symbols,),
        daemon=True,
        name="price_feed",
    )
    _ws_thread.start()
    logger.info("Price feed started (%s) for %s",
                "WebSocket" if use_websocket else "polling", symbols)


def stop_price_feed():
    """Stop the price feed."""
    global _running
    _running = False
    logger.info("Price feed stopped")


def is_feed_running() -> bool:
    return _running
