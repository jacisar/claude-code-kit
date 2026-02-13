"""Async API client for Polymarket Gamma and CLOB APIs.

Provides functions to fetch active markets and orderbook data
with concurrency control and structured error handling.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

from config.scanner import (
    GAMMA_API_URL,
    CLOB_API_URL,
    BATCH_SIZE,
    REQUEST_TIMEOUT,
    MIN_VOLUME,
    MARKET_LIMIT,
)
from src.polymarket.models import Market, OrderBook

logger = logging.getLogger(__name__)


async def fetch_active_markets(client: httpx.AsyncClient) -> list[Market]:
    """Fetch active markets from the Gamma API, filtered by volume.

    Markets are ordered by volume descending and filtered to only include
    those with CLOB token IDs and volume above the configured minimum.

    Args:
        client: Configured httpx async client.

    Returns:
        List of parsed Market objects that pass all filters.
    """
    params = {
        "active": "true",
        "closed": "false",
        "limit": MARKET_LIMIT,
        "order": "volume",
        "ascending": "false",
    }

    response = await client.get(f"{GAMMA_API_URL}/markets", params=params)
    response.raise_for_status()

    raw_markets = response.json()

    markets: list[Market] = []
    for raw in raw_markets:
        volume = float(raw.get("volume", 0))
        if volume < MIN_VOLUME:
            continue

        clob_token_ids = raw.get("clobTokenIds")
        if not clob_token_ids:
            continue

        market = Market.from_gamma_response(raw)
        if market is not None:
            markets.append(market)

    logger.info("Fetched %d active markets from Gamma API", len(markets))
    return markets


async def fetch_orderbook(
    client: httpx.AsyncClient, token_id: str
) -> OrderBook | None:
    """Fetch orderbook data for a single CLOB token.

    Args:
        client: Configured httpx async client.
        token_id: The CLOB token identifier.

    Returns:
        Parsed OrderBook or None if the request or parsing failed.
    """
    try:
        response = await client.get(
            f"{CLOB_API_URL}/book", params={"token_id": token_id}
        )
        response.raise_for_status()
        data = response.json()
        return OrderBook.from_api_response(data, token_id)
    except httpx.TimeoutException:
        logger.warning("Timeout fetching orderbook for token %s", token_id)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "HTTP %d fetching orderbook for token %s: %s",
            exc.response.status_code,
            token_id,
            exc.response.text,
        )
        return None
    except httpx.HTTPError as exc:
        logger.warning(
            "HTTP error fetching orderbook for token %s: %s", token_id, exc
        )
        return None
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning(
            "Failed to parse orderbook for token %s: %s", token_id, exc
        )
        return None


async def fetch_orderbooks_batch(
    client: httpx.AsyncClient, token_ids: list[str]
) -> dict[str, OrderBook]:
    """Fetch orderbooks for multiple tokens with concurrency control.

    Uses a semaphore limited to BATCH_SIZE concurrent requests to avoid
    overwhelming the CLOB API.

    Args:
        client: Configured httpx async client.
        token_ids: List of CLOB token identifiers.

    Returns:
        Dict mapping token_id to its OrderBook (tokens with failed fetches
        are omitted).
    """
    semaphore = asyncio.Semaphore(BATCH_SIZE)

    async def _fetch_with_semaphore(token_id: str) -> tuple[str, OrderBook | None]:
        async with semaphore:
            orderbook = await fetch_orderbook(client, token_id)
            return token_id, orderbook

    results = await asyncio.gather(
        *(_fetch_with_semaphore(tid) for tid in token_ids)
    )

    return {
        token_id: orderbook
        for token_id, orderbook in results
        if orderbook is not None
    }


def create_client() -> httpx.AsyncClient:
    """Create a configured httpx async client for Polymarket API calls.

    Returns:
        An httpx.AsyncClient with the configured request timeout.
    """
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
