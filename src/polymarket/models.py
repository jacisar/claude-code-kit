"""Dataclass models for Polymarket API data structures."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OrderBook:
    """Represents an order book for a single token on Polymarket CLOB.

    Bids are sorted descending by price (highest first).
    Asks are sorted ascending by price (lowest first).
    Prices and sizes arrive as strings from the API and are converted to float on access.
    """

    bids: list[dict[str, str]]
    asks: list[dict[str, str]]
    token_id: str

    def __post_init__(self) -> None:
        """Sort bids descending and asks ascending by price."""
        self.bids = sorted(
            self.bids, key=lambda b: float(b.get("price", "0")), reverse=True
        )
        self.asks = sorted(
            self.asks, key=lambda a: float(a.get("price", "0"))
        )

    @property
    def best_bid(self) -> float | None:
        """Highest bid price, or None if no bids exist."""
        if not self.bids:
            return None
        return float(self.bids[0]["price"])

    @property
    def best_ask(self) -> float | None:
        """Lowest ask price, or None if no asks exist."""
        if not self.asks:
            return None
        return float(self.asks[0]["price"])

    @property
    def best_bid_size(self) -> float | None:
        """Size at the best bid, or None if no bids exist."""
        if not self.bids:
            return None
        return float(self.bids[0]["size"])

    @property
    def best_ask_size(self) -> float | None:
        """Size at the best ask, or None if no asks exist."""
        if not self.asks:
            return None
        return float(self.asks[0]["size"])

    @classmethod
    def from_api_response(cls, data: dict, token_id: str) -> OrderBook:
        """Parse a CLOB API order book response into an OrderBook instance.

        Args:
            data: Raw API response dict, expected to contain "bids" and "asks" lists.
            token_id: The token ID this order book belongs to.

        Returns:
            An OrderBook instance with parsed bids and asks.
        """
        bids = data.get("bids", []) or []
        asks = data.get("asks", []) or []
        return cls(bids=bids, asks=asks, token_id=token_id)


@dataclass
class Market:
    """Represents a Polymarket prediction market from the Gamma API.

    Tokens are stored as a list of dicts with "token_id" and "outcome" keys.
    """

    condition_id: str
    question: str
    slug: str
    tokens: list[dict[str, str]]
    active: bool
    volume: float
    event_slug: str = ""

    @classmethod
    def from_gamma_response(cls, data: dict) -> Market | None:
        """Parse a Gamma API market response into a Market instance.

        The Gamma API returns clobTokenIds and outcomePrices as JSON-encoded strings,
        and outcomes as a comma-separated string (e.g. "Yes, No").

        Args:
            data: Raw Gamma API response dict for a single market.

        Returns:
            A Market instance, or None if the data is missing or malformed.
        """
        try:
            condition_id = data["conditionId"]
            question = data["question"]
            slug = data.get("slug", "")
            active = data.get("active", False)
            volume = float(data.get("volume", 0))

            # event_slug is nested inside events[0].slug
            events = data.get("events", [])
            event_slug = events[0].get("slug", "") if events else ""

            # clobTokenIds is a JSON string like '["token1", "token2"]'
            token_ids = json.loads(data["clobTokenIds"])

            # outcomePrices is a JSON string like '["0.55", "0.45"]'
            outcome_prices_raw = data.get("outcomePrices", "[]")
            json.loads(outcome_prices_raw)  # validate it parses, prices stored on order book

            # outcomes is a JSON string like '["Yes", "No"]'
            outcomes_raw = data.get("outcomes", "[]")
            outcomes = json.loads(outcomes_raw)

            # Build token list by zipping token IDs with their outcomes
            tokens = [
                {"token_id": tid, "outcome": outcome}
                for tid, outcome in zip(token_ids, outcomes)
            ]

            return cls(
                condition_id=condition_id,
                question=question,
                slug=slug,
                tokens=tokens,
                active=active,
                volume=volume,
                event_slug=event_slug,
            )
        except (KeyError, json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse Gamma market response: %s", exc)
            return None


@dataclass
class Opportunity:
    """Represents a detected arbitrage or trading opportunity.

    Attributes:
        market_question: The market question text.
        arb_type: Type of arbitrage - "BUY", "SELL", or "MULTI".
        profit_pct: Expected profit as a percentage.
        max_size: Maximum position size in USDC.
        max_profit_usd: Maximum profit in USD at max_size.
        yes_price: Current YES token price.
        no_price: Current NO token price.
        event_slug: Slug of the parent event.
        details: Human-readable description of the opportunity.
    """

    market_question: str
    arb_type: str
    profit_pct: float
    max_size: float
    max_profit_usd: float
    yes_price: float
    no_price: float
    event_slug: str = ""
    details: str = ""
