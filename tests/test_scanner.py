"""Tests for Polymarket arbitrage scanner functions."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.polymarket.models import Market, OrderBook, Opportunity
from src.polymarket.scanner import check_binary_arbitrage, check_multi_outcome_arbitrage


def _make_market(
    question: str = "Test market",
    tokens: list[dict[str, str]] | None = None,
    event_slug: str = "test-event",
) -> Market:
    """Helper to create a Market instance for tests."""
    if tokens is None:
        tokens = [
            {"token_id": "yes_token", "outcome": "Yes"},
            {"token_id": "no_token", "outcome": "No"},
        ]
    return Market(
        condition_id="0xtest",
        question=question,
        slug="test-market",
        tokens=tokens,
        active=True,
        volume=100000.0,
        event_slug=event_slug,
    )


def _make_orderbook(
    token_id: str,
    bids: list[tuple[str, str]] | None = None,
    asks: list[tuple[str, str]] | None = None,
) -> OrderBook:
    """Helper to create an OrderBook instance for tests.

    Args:
        token_id: Token identifier for this order book.
        bids: List of (price, size) tuples for bid side.
        asks: List of (price, size) tuples for ask side.
    """
    bid_dicts = [{"price": p, "size": s} for p, s in (bids or [])]
    ask_dicts = [{"price": p, "size": s} for p, s in (asks or [])]
    return OrderBook(bids=bid_dicts, asks=ask_dicts, token_id=token_id)


class TestCheckBinaryArbitrage:
    """Tests for check_binary_arbitrage function."""

    def test_buy_arbitrage_detected(self) -> None:
        """YES ask=0.45, NO ask=0.50 -> total 0.95, profit ~5%."""
        market = _make_market()

        yes_book = _make_orderbook(
            token_id="yes_token",
            asks=[("0.45", "100")],
        )
        no_book = _make_orderbook(
            token_id="no_token",
            asks=[("0.50", "80")],
        )

        opps = check_binary_arbitrage(market, yes_book, no_book)

        assert len(opps) == 1
        opp = opps[0]
        assert opp.arb_type == "BUY"
        assert opp.profit_pct == pytest.approx(0.05, abs=1e-9)
        assert opp.max_size == 80.0
        assert opp.market_question == "Test market"
        assert opp.yes_price == 0.45
        assert opp.no_price == 0.50

    def test_sell_arbitrage_detected(self) -> None:
        """YES bid=0.55, NO bid=0.50 -> total 1.05, profit ~5%."""
        market = _make_market()

        yes_book = _make_orderbook(
            token_id="yes_token",
            bids=[("0.55", "120")],
        )
        no_book = _make_orderbook(
            token_id="no_token",
            bids=[("0.50", "90")],
        )

        opps = check_binary_arbitrage(market, yes_book, no_book)

        assert len(opps) == 1
        opp = opps[0]
        assert opp.arb_type == "SELL"
        assert opp.profit_pct == pytest.approx(0.05, abs=1e-9)
        assert opp.max_size == 90.0
        assert opp.yes_price == 0.55
        assert opp.no_price == 0.50

    def test_no_arbitrage(self) -> None:
        """No buy arb (asks sum > 1.0) and no sell arb (bids sum < 1.0)."""
        market = _make_market()

        yes_book = _make_orderbook(
            token_id="yes_token",
            bids=[("0.45", "100")],
            asks=[("0.55", "100")],
        )
        no_book = _make_orderbook(
            token_id="no_token",
            bids=[("0.45", "100")],
            asks=[("0.50", "100")],
        )

        opps = check_binary_arbitrage(market, yes_book, no_book)

        assert opps == []

    def test_empty_orderbook_skipped(self) -> None:
        """One book has no asks/bids - should return empty list without crashing."""
        market = _make_market()

        yes_book = _make_orderbook(
            token_id="yes_token",
            asks=[("0.45", "100")],
        )
        # NO book is completely empty
        no_book = _make_orderbook(token_id="no_token")

        opps = check_binary_arbitrage(market, yes_book, no_book)

        assert opps == []

    def test_below_threshold_filtered(self) -> None:
        """Profit just below MIN_PROFIT_THRESHOLD (0.1% = 0.001) is filtered out."""
        market = _make_market()

        # Asks sum to 0.9995 -> profit = 0.0005 (0.05%), below 0.001 threshold
        yes_book = _make_orderbook(
            token_id="yes_token",
            asks=[("0.4995", "100")],
        )
        no_book = _make_orderbook(
            token_id="no_token",
            asks=[("0.5000", "100")],
        )

        with patch("src.polymarket.scanner.MIN_PROFIT_THRESHOLD", 0.001):
            opps = check_binary_arbitrage(market, yes_book, no_book)

        assert opps == []


class TestCheckMultiOutcomeArbitrage:
    """Tests for check_multi_outcome_arbitrage function."""

    def test_multi_outcome_buy_arbitrage(self) -> None:
        """3 outcomes with asks summing to 0.90 -> 10% profit."""
        books: list[tuple[str, OrderBook]] = [
            (
                "Outcome A",
                _make_orderbook(token_id="token_a", asks=[("0.30", "50")]),
            ),
            (
                "Outcome B",
                _make_orderbook(token_id="token_b", asks=[("0.30", "60")]),
            ),
            (
                "Outcome C",
                _make_orderbook(token_id="token_c", asks=[("0.30", "70")]),
            ),
        ]

        opps = check_multi_outcome_arbitrage(
            market_question="Multi-outcome test",
            books=books,
            event_slug="multi-event",
        )

        assert len(opps) == 1
        opp = opps[0]
        assert opp.arb_type == "MULTI"
        assert opp.profit_pct == pytest.approx(0.10, abs=1e-9)
        assert opp.max_size == 50.0  # min of 50, 60, 70
        assert opp.market_question == "Multi-outcome test"
        assert opp.event_slug == "multi-event"

    def test_multi_outcome_no_arbitrage(self) -> None:
        """3 outcomes with asks summing to 1.05 -> no arbitrage."""
        books: list[tuple[str, OrderBook]] = [
            (
                "Outcome A",
                _make_orderbook(token_id="token_a", asks=[("0.35", "50")]),
            ),
            (
                "Outcome B",
                _make_orderbook(token_id="token_b", asks=[("0.35", "60")]),
            ),
            (
                "Outcome C",
                _make_orderbook(token_id="token_c", asks=[("0.35", "70")]),
            ),
        ]

        opps = check_multi_outcome_arbitrage(
            market_question="No arb here",
            books=books,
            event_slug="no-arb-event",
        )

        assert opps == []
