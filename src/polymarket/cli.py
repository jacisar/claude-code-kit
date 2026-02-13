"""CLI entry point for the Polymarket arbitrage scanner.

Provides a command-line interface that fetches active markets,
scans for arbitrage opportunities, and displays results as an ASCII table.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time

from src.polymarket.api import create_client, fetch_active_markets
from src.polymarket.scanner import scan_markets
from src.polymarket.models import Opportunity

logger = logging.getLogger(__name__)

# Table formatting constants
COLUMN_MARKET_WIDTH = 50
COLUMN_TYPE_WIDTH = 6
COLUMN_PROFIT_WIDTH = 9
COLUMN_YES_WIDTH = 9
COLUMN_NO_WIDTH = 9
COLUMN_SIZE_WIDTH = 12
COLUMN_MAX_PROFIT_WIDTH = 14


def format_table(opportunities: list[Opportunity]) -> str:
    """Format a list of arbitrage opportunities as an ASCII table.

    Columns: Market (left-aligned, truncated to 50 chars), Type, Profit %,
    YES Price, NO Price, Max Size, Max Profit USD (all right-aligned).

    Args:
        opportunities: List of Opportunity dataclass instances to display.

    Returns:
        A multi-line string containing the formatted ASCII table.
    """
    header = (
        f"{'Market':<{COLUMN_MARKET_WIDTH}} "
        f"{'Type':>{COLUMN_TYPE_WIDTH}} "
        f"{'Profit %':>{COLUMN_PROFIT_WIDTH}} "
        f"{'YES Price':>{COLUMN_YES_WIDTH}} "
        f"{'NO Price':>{COLUMN_NO_WIDTH}} "
        f"{'Max Size':>{COLUMN_SIZE_WIDTH}} "
        f"{'Max Profit USD':>{COLUMN_MAX_PROFIT_WIDTH}}"
    )

    separator = "-" * len(header)

    lines = [header, separator]

    for opp in opportunities:
        market_name = opp.market_question
        if len(market_name) > COLUMN_MARKET_WIDTH:
            market_name = market_name[: COLUMN_MARKET_WIDTH - 3] + "..."

        row = (
            f"{market_name:<{COLUMN_MARKET_WIDTH}} "
            f"{opp.arb_type:>{COLUMN_TYPE_WIDTH}} "
            f"{opp.profit_pct * 100:>{COLUMN_PROFIT_WIDTH}.2f} "
            f"{opp.yes_price:>{COLUMN_YES_WIDTH}.4f} "
            f"{opp.no_price:>{COLUMN_NO_WIDTH}.4f} "
            f"{opp.max_size:>{COLUMN_SIZE_WIDTH}.2f} "
            f"{opp.max_profit_usd:>{COLUMN_MAX_PROFIT_WIDTH}.2f}"
        )
        lines.append(row)

    return "\n".join(lines)


async def run() -> int:
    """Main async function that orchestrates the scanning pipeline.

    Configures logging, loads environment, fetches markets, scans for
    arbitrage opportunities, and prints the results.

    Returns:
        0 if opportunities were found, 1 otherwise.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Load .env file if python-dotenv is available
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        logger.debug("python-dotenv not installed, skipping .env loading")

    start_time = time.monotonic()

    try:
        async with create_client() as client:
            logger.info("Fetching active markets...")
            markets = await fetch_active_markets(client)
            logger.info("Scanning %d markets for arbitrage opportunities...", len(markets))
            opportunities = await scan_markets(client, markets)

        elapsed = time.monotonic() - start_time
        logger.info("Scan completed in %.2f seconds", elapsed)

        if opportunities:
            # Sort by profit percentage descending
            opportunities.sort(key=lambda o: o.profit_pct, reverse=True)

            print("\nPolymarket Arbitrage Scanner")
            print("=" * 40)
            print()
            print(format_table(opportunities))
            print()
            best_profit = max(o.profit_pct for o in opportunities)
            print(
                f"Found {len(opportunities)} opportunity(ies). "
                f"Best profit: {best_profit * 100:.2f}%"
            )
            return 0

        print("No arbitrage opportunities found.")
        return 1

    except KeyboardInterrupt:
        elapsed = time.monotonic() - start_time
        logger.info("Interrupted by user after %.2f seconds", elapsed)
        return 130


def main() -> None:
    """Synchronous entry point for the Polymarket arbitrage scanner CLI."""
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
