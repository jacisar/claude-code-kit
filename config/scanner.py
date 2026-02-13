"""Configuration for Polymarket arbitrage scanner.

All values are loaded from environment variables with no silent defaults
for required settings. Override via .env file or shell environment.
"""

import os

# API base URLs
GAMMA_API_URL = os.getenv("GAMMA_API_URL", "https://gamma-api.polymarket.com")
CLOB_API_URL = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")

# Scanner parameters (with sensible defaults for non-secret config)
MIN_PROFIT_THRESHOLD = float(os.getenv("MIN_PROFIT_THRESHOLD", "0.001"))  # 0.1%
MIN_VOLUME = float(os.getenv("MIN_VOLUME", "10000"))  # Minimum market volume in USD
MARKET_LIMIT = int(os.getenv("MARKET_LIMIT", "100"))  # Markets to fetch from Gamma
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20"))  # Concurrent orderbook requests
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "15"))  # httpx timeout in seconds
