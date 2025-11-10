"""
AlphaVantage API client for ETF holdings and financial data.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class AlphaVantageClient:
    """Client for interacting with AlphaVantage API with automatic key rotation."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize AlphaVantage client.

        Args:
            api_key: Optional single API key override. If not provided, keys are
                loaded from environment (supports multiple keys).
        """
        self.api_keys: List[str] = []
        if api_key:
            self.api_keys = [api_key]
        else:
            self.api_keys = self._load_api_keys_from_env()

        if not self.api_keys:
            raise ValueError(
                "AlphaVantage API key not found. Set ALPHAVANTAGE_API_KEY or "
                "ALPHAVANTAGE_API_KEYS in the environment/.env file."
            )

        self.current_key_index = 0
        self.last_url: Optional[str] = None
        self.last_key_used: Optional[str] = None

    @staticmethod
    def _load_api_keys_from_env() -> List[str]:
        """Load API keys from environment variables."""
        keys: List[str] = []

        # ALPHAVANTAGE_API_KEYS can contain comma/semicolon/whitespace-separated list
        raw_multi = os.getenv("ALPHAVANTAGE_API_KEYS", "")
        if raw_multi:
            for part in raw_multi.replace(";", ",").split(","):
                candidate = part.strip()
                if candidate:
                    keys.append(candidate)

        # Collect prefixed keys (ALPHAVANTAGE_API_KEY, ALPHAVANTAGE_API_KEY_1, etc.)
        for env_key, value in os.environ.items():
            if env_key == "ALPHAVANTAGE_API_KEY" or env_key.startswith(
                "ALPHAVANTAGE_API_KEY_"
            ):
                candidate = value.strip()
                if candidate:
                    keys.append(candidate)

        # Preserve order but remove duplicates while maintaining insertion order
        seen = set()
        deduped: List[str] = []
        for key in keys:
            if key not in seen:
                deduped.append(key)
                seen.add(key)

        return deduped

    def _select_key(self, attempt: int) -> str:
        """Return API key for the given attempt index."""
        index = (self.current_key_index + attempt) % len(self.api_keys)
        return self.api_keys[index]

    def _advance_key(self, used_key: str):
        """Advance current key index to the key following `used_key`."""
        try:
            idx = self.api_keys.index(used_key)
        except ValueError:
            return
        self.current_key_index = (idx + 1) % len(self.api_keys)

    def _make_request(self, params: Dict[str, str]) -> Tuple[Dict[str, Any], str]:
        """
        Make a request to AlphaVantage API, rotating through available keys as needed.

        Args:
            params: Query parameters for the API request (without apikey).

        Returns:
            Tuple of (JSON response, key used).
        """
        last_exception: Optional[Exception] = None
        self.last_url = None
        self.last_key_used = None

        for attempt in range(len(self.api_keys)):
            key = self._select_key(attempt)
            params_with_key = {**params, "apikey": key}
            try:
                response = requests.get(self.BASE_URL, params=params_with_key, timeout=10)
                response.raise_for_status()
                self.last_url = response.url
                self.last_key_used = key
                print(
                    f"AlphaVantage request [{params.get('function')}|key#{attempt+1}]: {self.last_url}"
                )
                data = response.json()

                if "Note" in data:
                    # Rate limit hit for this key, rotate to next
                    print(
                        "AlphaVantage rate limit note received; rotating API key."
                    )
                    self._advance_key(key)
                    last_exception = ValueError(
                        f"AlphaVantage rate limit: {data['Note']} (url: {self.last_url})"
                    )
                    continue

                if "Error Message" in data:
                    # Invalid symbol or other error – propagate
                    raise ValueError(
                        f"AlphaVantage API error: {data['Error Message']} (url: {self.last_url})"
                    )

                # Success
                self._advance_key(key)
                return data, key

            except requests.exceptions.RequestException as e:
                failing_url = getattr(getattr(e, "request", None), "url", self.last_url)
                last_exception = ValueError(
                    f"Request to AlphaVantage failed: {e} (url: {failing_url})"
                )
                print(last_exception)
                self._advance_key(key)
                continue
            except ValueError as e:
                last_exception = e
                print(e)
                # advance only if it looks like rate limit; others re-raise
                if "rate limit" in str(e).lower():
                    self._advance_key(key)
                    continue
                raise

        # If all keys exhausted, raise last encountered exception
        if last_exception:
            raise last_exception
        raise ValueError("AlphaVantage request failed: no API keys available")

    def get_etf_profile(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Get ETF profile information including holdings.

        Args:
            symbol: ETF ticker symbol (e.g., 'SPY', 'VOO').

        Returns:
            DataFrame with ETF holdings or None if data unavailable.
        """
        try:
            params = {"function": "ETF_PROFILE", "symbol": symbol}
            data, _ = self._make_request(params)

            request_url = self.last_url
            if not data or "holdings" not in data:
                print(
                    f"No holdings data for {symbol} from AlphaVantage"
                    + (f" (url: {request_url})" if request_url else "")
                )
                return None

            holdings = data.get("holdings", [])
            if not holdings:
                print(
                    f"Empty holdings list for {symbol} from AlphaVantage"
                    + (f" (url: {request_url})" if request_url else "")
                )
                return None

            df = pd.DataFrame(holdings)

            # Standardize column names
            column_mapping = {
                "symbol": "Symbol",
                "name": "Name",
                "weight": "Weight",
                "shares": "Shares",
            }
            df.rename(columns=column_mapping, inplace=True)

            # Convert weight to decimal proportion if present
            if "Weight" in df.columns:
                weights = pd.to_numeric(df["Weight"], errors="coerce")
                if weights.notna().any():
                    max_weight = weights.max()
                    # If values look like percentages (e.g., 5.6) convert down
                    if max_weight and max_weight > 1.5:
                        weights = weights / 100.0
                    # If values are extremely small (e.g., 0.00056) scale up
                    elif max_weight and max_weight < 0.001:
                        weights = weights * 100.0
                    df["Weight"] = weights
            return df

        except Exception as e:
            url_info = f" (url: {self.last_url})" if self.last_url else ""
            print(f"Error fetching AlphaVantage data for {symbol}: {e}{url_info}")
            return None

    def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time quote for a symbol.

        Args:
            symbol: Ticker symbol.

        Returns:
            Dictionary with quote data or None if unavailable.
        """
        try:
            params = {"function": "GLOBAL_QUOTE", "symbol": symbol}
            data, _ = self._make_request(params)

            if "Global Quote" not in data:
                print(
                    f"No quote data for {symbol} from AlphaVantage"
                    + (f" (url: {self.last_url})" if self.last_url else "")
                )
                return None

            quote = data["Global Quote"]
            return {
                "symbol": quote.get("01. symbol"),
                "price": float(quote.get("05. price", 0)),
                "change": float(quote.get("09. change", 0)),
                "change_percent": quote.get("10. change percent", "0%"),
                "volume": int(quote.get("06. volume", 0)),
            }
        except Exception as e:
            url_info = f" (url: {self.last_url})" if self.last_url else ""
            print(f"Error fetching quote for {symbol}: {e}{url_info}")
            return None

    def get_company_overview(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get company overview including sector, industry, and fundamental data.

        Args:
            symbol: Stock ticker symbol.

        Returns:
            Dictionary with company data or None if unavailable.
        """
        try:
            params = {"function": "OVERVIEW", "symbol": symbol}
            data, _ = self._make_request(params)

            if not data or "Symbol" not in data:
                print(
                    f"No company overview for {symbol} from AlphaVantage"
                    + (f" (url: {self.last_url})" if self.last_url else "")
                )
                return None

            return {
                "symbol": data.get("Symbol"),
                "name": data.get("Name"),
                "sector": data.get("Sector"),
                "industry": data.get("Industry"),
                "market_cap": data.get("MarketCapitalization"),
                "pe_ratio": data.get("PERatio"),
                "dividend_yield": data.get("DividendYield"),
            }
        except Exception as e:
            url_info = f" (url: {self.last_url})" if self.last_url else ""
            print(f"Error fetching company overview for {symbol}: {e}{url_info}")
            return None

