"""Tests for Polymarket data models (OrderBook, Market)."""

from __future__ import annotations

import pytest

from src.polymarket.models import OrderBook, Market


class TestOrderBookFromApiResponse:
    """Tests for OrderBook.from_api_response class method."""

    def test_orderbook_from_api_response(self) -> None:
        """Parse a valid CLOB API response with multiple bids and asks."""
        data: dict = {
            "bids": [
                {"price": "0.45", "size": "100"},
                {"price": "0.44", "size": "50"},
            ],
            "asks": [
                {"price": "0.55", "size": "200"},
                {"price": "0.56", "size": "150"},
            ],
        }

        book = OrderBook.from_api_response(data, token_id="token_123")

        assert book.best_bid == 0.45
        assert book.best_ask == 0.55
        assert book.best_bid_size == 100.0
        assert book.best_ask_size == 200.0
        assert book.token_id == "token_123"

    def test_orderbook_empty(self) -> None:
        """Empty bids and asks result in None for all best_* properties."""
        data: dict = {"bids": [], "asks": []}

        book = OrderBook.from_api_response(data, token_id="token_empty")

        assert book.best_bid is None
        assert book.best_ask is None
        assert book.best_bid_size is None
        assert book.best_ask_size is None

    def test_orderbook_string_price_sorting(self) -> None:
        """Verify bids are sorted descending and asks ascending even with unsorted input."""
        data: dict = {
            "bids": [
                {"price": "0.30", "size": "10"},
                {"price": "0.50", "size": "20"},
                {"price": "0.40", "size": "15"},
            ],
            "asks": [
                {"price": "0.70", "size": "25"},
                {"price": "0.55", "size": "30"},
                {"price": "0.60", "size": "35"},
            ],
        }

        book = OrderBook.from_api_response(data, token_id="token_sort")

        # Best bid should be the highest price
        assert book.best_bid == 0.50
        assert book.best_bid_size == 20.0

        # Best ask should be the lowest price
        assert book.best_ask == 0.55
        assert book.best_ask_size == 30.0

        # Verify full sort order: bids descending
        bid_prices = [float(b["price"]) for b in book.bids]
        assert bid_prices == [0.50, 0.40, 0.30]

        # Verify full sort order: asks ascending
        ask_prices = [float(a["price"]) for a in book.asks]
        assert ask_prices == [0.55, 0.60, 0.70]


class TestMarketFromGammaResponse:
    """Tests for Market.from_gamma_response class method."""

    def test_market_from_gamma_response(self) -> None:
        """Parse a Gamma API response with JSON string fields."""
        data: dict = {
            "conditionId": "0xabc123",
            "question": "Will Bitcoin reach $100k?",
            "slug": "will-bitcoin-reach-100k",
            "outcomes": '["Yes", "No"]',
            "clobTokenIds": '["token_yes_123", "token_no_456"]',
            "outcomePrices": '["0.65", "0.35"]',
            "active": True,
            "volume": 50000.0,
            "events": [{"slug": "bitcoin-100k"}],
        }

        market = Market.from_gamma_response(data)

        assert market is not None
        assert market.condition_id == "0xabc123"
        assert market.question == "Will Bitcoin reach $100k?"
        assert market.slug == "will-bitcoin-reach-100k"
        assert market.active is True
        assert market.volume == 50000.0
        assert market.event_slug == "bitcoin-100k"

        # Tokens should be parsed from JSON string fields
        assert len(market.tokens) == 2
        assert market.tokens[0]["token_id"] == "token_yes_123"
        assert market.tokens[0]["outcome"] == "Yes"
        assert market.tokens[1]["token_id"] == "token_no_456"
        assert market.tokens[1]["outcome"] == "No"

    def test_market_from_gamma_response_malformed(self) -> None:
        """Malformed clobTokenIds returns None."""
        data: dict = {
            "conditionId": "0xabc",
            "question": "Bad market",
            "slug": "bad",
            "outcomes": '["Yes", "No"]',
            "clobTokenIds": "not-json",
            "outcomePrices": "not-json",
            "active": True,
            "volume": 1000.0,
        }

        market = Market.from_gamma_response(data)

        assert market is None

    def test_market_from_gamma_missing_fields(self) -> None:
        """Missing required fields (condition_id, clobTokenIds) returns None."""
        # Missing conditionId entirely
        data_no_condition: dict = {
            "question": "Some question",
            "slug": "some-slug",
            "outcomes": '["Yes", "No"]',
            "clobTokenIds": '["t1", "t2"]',
            "outcomePrices": '["0.5", "0.5"]',
            "active": True,
            "volume": 100.0,
        }
        assert Market.from_gamma_response(data_no_condition) is None

        # Missing clobTokenIds entirely
        data_no_tokens: dict = {
            "conditionId": "0xdef",
            "question": "Another question",
            "slug": "another",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.5", "0.5"]',
            "active": True,
            "volume": 100.0,
        }
        assert Market.from_gamma_response(data_no_tokens) is None
