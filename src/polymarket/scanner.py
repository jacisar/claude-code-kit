"""Core arbitrage detection logic for Polymarket binary and multi-outcome markets.

Scans order books for pricing inefficiencies where the combined cost of
buying (or selling) all outcomes is less (or more) than 1.0, indicating
a risk-free arbitrage opportunity.
"""

from __future__ import annotations

import asyncio
import logging

from src.polymarket.models import Market, OrderBook, Opportunity
from src.polymarket.api import fetch_orderbooks_batch
from config.scanner import MIN_PROFIT_THRESHOLD

logger = logging.getLogger(__name__)


def check_binary_arbitrage(
    market: Market, yes_book: OrderBook, no_book: OrderBook
) -> list[Opportunity]:
    """Check a binary (YES/NO) market for buy-side and sell-side arbitrage.

    BUY arbitrage exists when the sum of best asks is less than 1.0,
    meaning you can buy both YES and NO for less than the guaranteed payout.

    SELL arbitrage exists when the sum of best bids exceeds 1.0,
    meaning you can sell both YES and NO for more than the guaranteed payout.

    Args:
        market: The binary market to check.
        yes_book: Order book for the YES outcome token.
        no_book: Order book for the NO outcome token.

    Returns:
        List of Opportunity objects for any arbitrage found (0, 1, or 2 items).
    """
    opportunities: list[Opportunity] = []

    # --- BUY arbitrage: buy both sides for less than 1.0 ---
    yes_ask = yes_book.best_ask
    no_ask = no_book.best_ask

    if yes_ask is not None and no_ask is not None:
        combined_ask = yes_ask + no_ask
        if combined_ask < 1.0:
            profit_pct = 1.0 - combined_ask
            if profit_pct >= MIN_PROFIT_THRESHOLD:
                max_size = min(yes_book.best_ask_size, no_book.best_ask_size)
                max_profit_usd = profit_pct * max_size
                opportunities.append(
                    Opportunity(
                        market_question=market.question,
                        arb_type="BUY",
                        profit_pct=profit_pct,
                        max_size=max_size,
                        max_profit_usd=max_profit_usd,
                        yes_price=yes_ask,
                        no_price=no_ask,
                        event_slug=market.event_slug,
                        details=(
                            f"BUY arb: YES ask={yes_ask:.4f} + NO ask={no_ask:.4f} "
                            f"= {combined_ask:.4f} < 1.0 | "
                            f"profit={profit_pct:.4f} ({profit_pct * 100:.2f}%) | "
                            f"max_size={max_size:.2f} | max_profit=${max_profit_usd:.2f}"
                        ),
                    )
                )
                logger.info(
                    "BUY arb found: %s | profit=%.4f | max_profit=$%.2f",
                    market.question,
                    profit_pct,
                    max_profit_usd,
                )

    # --- SELL arbitrage: sell both sides for more than 1.0 ---
    yes_bid = yes_book.best_bid
    no_bid = no_book.best_bid

    if yes_bid is not None and no_bid is not None:
        combined_bid = yes_bid + no_bid
        if combined_bid > 1.0:
            profit_pct = combined_bid - 1.0
            if profit_pct >= MIN_PROFIT_THRESHOLD:
                max_size = min(yes_book.best_bid_size, no_book.best_bid_size)
                max_profit_usd = profit_pct * max_size
                opportunities.append(
                    Opportunity(
                        market_question=market.question,
                        arb_type="SELL",
                        profit_pct=profit_pct,
                        max_size=max_size,
                        max_profit_usd=max_profit_usd,
                        yes_price=yes_bid,
                        no_price=no_bid,
                        event_slug=market.event_slug,
                        details=(
                            f"SELL arb: YES bid={yes_bid:.4f} + NO bid={no_bid:.4f} "
                            f"= {combined_bid:.4f} > 1.0 | "
                            f"profit={profit_pct:.4f} ({profit_pct * 100:.2f}%) | "
                            f"max_size={max_size:.2f} | max_profit=${max_profit_usd:.2f}"
                        ),
                    )
                )
                logger.info(
                    "SELL arb found: %s | profit=%.4f | max_profit=$%.2f",
                    market.question,
                    profit_pct,
                    max_profit_usd,
                )

    return opportunities


def check_multi_outcome_arbitrage(
    market_question: str,
    books: list[tuple[str, OrderBook]],
    event_slug: str,
) -> list[Opportunity]:
    """Check a multi-outcome market (3+ outcomes) for buy-side and sell-side arbitrage.

    BUY arbitrage exists when the sum of all best asks is less than 1.0.
    SELL arbitrage exists when the sum of all best bids exceeds 1.0.

    Args:
        market_question: The market question text.
        books: List of (outcome_name, OrderBook) tuples for each outcome.
        event_slug: Slug of the parent event.

    Returns:
        List of Opportunity objects for any arbitrage found (0, 1, or 2 items).
    """
    opportunities: list[Opportunity] = []

    # --- BUY arbitrage: sum of all asks < 1.0 ---
    all_asks_valid = all(book.best_ask is not None for _, book in books)
    if all_asks_valid:
        sum_of_asks = sum(book.best_ask for _, book in books)
        if sum_of_asks < 1.0:
            profit_pct = 1.0 - sum_of_asks
            if profit_pct >= MIN_PROFIT_THRESHOLD:
                max_size = min(book.best_ask_size for _, book in books)
                max_profit_usd = profit_pct * max_size
                outcome_details = ", ".join(
                    f"{name}={book.best_ask:.4f}" for name, book in books
                )
                opportunities.append(
                    Opportunity(
                        market_question=market_question,
                        arb_type="MULTI",
                        profit_pct=profit_pct,
                        max_size=max_size,
                        max_profit_usd=max_profit_usd,
                        yes_price=sum_of_asks,
                        no_price=0.0,
                        event_slug=event_slug,
                        details=(
                            f"MULTI BUY arb: sum_asks={sum_of_asks:.4f} < 1.0 | "
                            f"outcomes: [{outcome_details}] | "
                            f"profit={profit_pct:.4f} ({profit_pct * 100:.2f}%) | "
                            f"max_size={max_size:.2f} | max_profit=${max_profit_usd:.2f}"
                        ),
                    )
                )
                logger.info(
                    "MULTI BUY arb found: %s | profit=%.4f | max_profit=$%.2f",
                    market_question,
                    profit_pct,
                    max_profit_usd,
                )

    # --- SELL arbitrage: sum of all bids > 1.0 ---
    all_bids_valid = all(book.best_bid is not None for _, book in books)
    if all_bids_valid:
        sum_of_bids = sum(book.best_bid for _, book in books)
        if sum_of_bids > 1.0:
            profit_pct = sum_of_bids - 1.0
            if profit_pct >= MIN_PROFIT_THRESHOLD:
                max_size = min(book.best_bid_size for _, book in books)
                max_profit_usd = profit_pct * max_size
                outcome_details = ", ".join(
                    f"{name}={book.best_bid:.4f}" for name, book in books
                )
                opportunities.append(
                    Opportunity(
                        market_question=market_question,
                        arb_type="MULTI",
                        profit_pct=profit_pct,
                        max_size=max_size,
                        max_profit_usd=max_profit_usd,
                        yes_price=0.0,
                        no_price=sum_of_bids,
                        event_slug=event_slug,
                        details=(
                            f"MULTI SELL arb: sum_bids={sum_of_bids:.4f} > 1.0 | "
                            f"outcomes: [{outcome_details}] | "
                            f"profit={profit_pct:.4f} ({profit_pct * 100:.2f}%) | "
                            f"max_size={max_size:.2f} | max_profit=${max_profit_usd:.2f}"
                        ),
                    )
                )
                logger.info(
                    "MULTI SELL arb found: %s | profit=%.4f | max_profit=$%.2f",
                    market_question,
                    profit_pct,
                    max_profit_usd,
                )

    return opportunities


async def scan_markets(
    client, markets: list[Market]
) -> list[Opportunity]:
    """Scan a list of markets for arbitrage opportunities.

    Fetches all order books in a single batch call, then checks each market
    for binary or multi-outcome arbitrage.

    Args:
        client: An httpx.AsyncClient instance for making API requests.
        markets: List of Market objects to scan.

    Returns:
        List of Opportunity objects sorted by profit_pct descending.
    """
    # Collect all token IDs across all markets
    all_token_ids: list[str] = []
    for market in markets:
        for token in market.tokens:
            all_token_ids.append(token["token_id"])

    logger.info(
        "Scanning %d markets with %d total tokens",
        len(markets),
        len(all_token_ids),
    )

    # Fetch all orderbooks in one batch
    orderbooks: dict[str, OrderBook] = await fetch_orderbooks_batch(
        client, all_token_ids
    )

    logger.info(
        "Fetched %d orderbooks out of %d requested",
        len(orderbooks),
        len(all_token_ids),
    )

    opportunities: list[Opportunity] = []

    for market in markets:
        num_outcomes = len(market.tokens)

        if num_outcomes == 2:
            # Binary market: first token treated as "yes", second as "no"
            # Works for Yes/No, Over/Under, and other binary pairs
            yes_token_id = market.tokens[0]["token_id"]
            no_token_id = market.tokens[1]["token_id"]

            yes_book = orderbooks.get(yes_token_id)
            no_book = orderbooks.get(no_token_id)

            if yes_book is None or no_book is None:
                logger.warning(
                    "Missing orderbook for binary market: %s", market.question
                )
                continue

            found = check_binary_arbitrage(market, yes_book, no_book)
            opportunities.extend(found)

        elif num_outcomes >= 3:
            # Multi-outcome market: collect all outcome orderbooks
            books: list[tuple[str, OrderBook]] = []
            missing_book = False

            for token in market.tokens:
                token_id = token["token_id"]
                outcome_name = token["outcome"]
                book = orderbooks.get(token_id)

                if book is None:
                    logger.warning(
                        "Missing orderbook for token %s (%s) in market: %s",
                        token_id,
                        outcome_name,
                        market.question,
                    )
                    missing_book = True
                    break

                books.append((outcome_name, book))

            if missing_book:
                continue

            found = check_multi_outcome_arbitrage(
                market.question, books, market.event_slug
            )
            opportunities.extend(found)

    # Sort by profit_pct descending (best opportunities first)
    opportunities.sort(key=lambda o: o.profit_pct, reverse=True)

    logger.info(
        "Scan complete: found %d opportunities across %d markets",
        len(opportunities),
        len(markets),
    )

    return opportunities
