"""
Financial Modeling Prep (FMP) API client for ETF holdings and financial data.
"""

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class FMPClient:
    """Client for interacting with Financial Modeling Prep API with automatic key rotation."""

    BASE_URL = "https://financialmodelingprep.com"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize FMP client.

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
                "FMP API key not found. Set FMP_API_KEY or FMP_API_KEYS in the environment/.env file."
            )

        self.current_key_index = 0
        self.last_url: Optional[str] = None
        self.last_key_used: Optional[str] = None

    @staticmethod
    def _load_api_keys_from_env() -> List[str]:
        """Load API keys from environment variables."""
        keys: List[str] = []

        # FMP_API_KEYS can contain comma/semicolon/whitespace-separated list
        raw_multi = os.getenv("FMP_API_KEYS", "")
        if raw_multi:
            for part in raw_multi.replace(";", ",").split(","):
                candidate = part.strip()
                if candidate:
                    keys.append(candidate)

        # Collect prefixed keys (FMP_API_KEY, FMP_API_KEY_1, etc.)
        for env_key, value in os.environ.items():
            if env_key == "FMP_API_KEY" or env_key.startswith("FMP_API_KEY_"):
                candidate = value.strip()
                if candidate:
                    keys.append(candidate)

        # Remove duplicates while maintaining order
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

    def _make_request(self, endpoint: str, params: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Make a request to FMP API, rotating through available keys as needed.

        Args:
            endpoint: API endpoint path (e.g., '/stable/etf/holdings').
            params: Optional query parameters (without apikey).

        Returns:
            JSON response (dict or list).
        """
        if params is None:
            params = {}

        last_exception: Optional[Exception] = None
        self.last_url = None
        self.last_key_used = None

        for attempt in range(len(self.api_keys)):
            key = self._select_key(attempt)
            params_with_key = {**params, "apikey": key}
            url = f"{self.BASE_URL}{endpoint}"

            try:
                response = requests.get(url, params=params_with_key, timeout=10)
                response.raise_for_status()
                self.last_url = response.url
                self.last_key_used = key

                # Parse response
                data = response.json()

                # FMP returns different error structures
                if isinstance(data, dict):
                    # Check for error messages
                    if "Error Message" in data:
                        error_msg = data["Error Message"]
                        print(f"FMP API error: {error_msg} (url: {self.last_url})")
                        raise ValueError(f"FMP API error: {error_msg} (url: {self.last_url})")

                    # Check for rate limit or information messages
                    if "Information" in data or "Note" in data:
                        info_msg = data.get("Information") or data.get("Note", "")
                        print(
                            f"FMP rate limit/info message received (key#{attempt+1}); rotating API key: {info_msg} (url: {self.last_url})"
                        )
                        self._advance_key(key)
                        last_exception = ValueError(
                            f"FMP rate limit/info: {info_msg} (url: {self.last_url})"
                        )
                        continue

                # Log successful request
                print(f"FMP request [key#{attempt+1}|{endpoint}]: {self.last_url}")

                # Success
                self._advance_key(key)
                return data

            except requests.exceptions.RequestException as e:
                failing_url = getattr(getattr(e, "request", None), "url", self.last_url)
                last_exception = ValueError(
                    f"Request to FMP failed: {e} (url: {failing_url})"
                )
                print(last_exception)
                self._advance_key(key)
                continue
            except ValueError as e:
                last_exception = e
                print(e)
                # advance only if it looks like rate limit; others re-raise
                if "rate limit" in str(e).lower() or "info" in str(e).lower():
                    self._advance_key(key)
                    continue
                raise

        # If all keys exhausted, raise last encountered exception
        if last_exception:
            raise last_exception
        raise ValueError("FMP request failed: no API keys available")

    @staticmethod
    def _normalise_weights(series: pd.Series) -> pd.Series:
        """Normalise weight series to decimal proportions."""
        weights = pd.to_numeric(series, errors="coerce")
        if weights.notna().any():
            max_weight = weights.max()
            if max_weight and max_weight > 1.5:
                weights = weights / 100.0
            elif max_weight and max_weight < 0.001:
                weights = weights * 100.0
        return weights

    def _request_with_fallbacks(
        self, endpoints: Iterable[str], params: Dict[str, str]
    ) -> Tuple[Optional[Any], Optional[str]]:
        """
        Try multiple endpoints (e.g., stable vs api/v3) until data is returned.
        """
        last_error: Optional[Exception] = None
        for endpoint in endpoints:
            try:
                data = self._make_request(endpoint, params)
                if isinstance(data, dict) and not data:
                    # Empty dict - try next endpoint
                    continue
                if isinstance(data, list) and len(data) == 0:
                    # Empty list - try next endpoint
                    continue
                return data, endpoint
            except ValueError as exc:
                last_error = exc
                continue
            except Exception as exc:
                last_error = exc
                continue

        if last_error:
            print(f"FMP request fallbacks exhausted: {last_error}")
        return None, None

    def get_etf_holdings(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Get ETF holdings information.

        Args:
            symbol: ETF ticker symbol (e.g., 'SPY', 'VOO').

        Returns:
            DataFrame with ETF holdings or None if data unavailable.
        """
        try:
            params = {"symbol": symbol.upper()}
            data, used_endpoint = self._request_with_fallbacks(
                ["/api/v3/etf-holder", "/api/v4/etf-holder"], params
            )

            if not data:
                print(
                    f"No holdings data for {symbol} from FMP"
                    + (f" (url: {self.last_url})" if self.last_url else "")
                )
                return None

            # FMP returns a list of holdings
            if isinstance(data, list):
                df = pd.DataFrame(data)
            else:
                print(
                    f"Unexpected FMP response format for {symbol}"
                    + (f" (url: {self.last_url})" if self.last_url else "")
                )
                return None

            if df.empty:
                print(
                    f"Empty holdings list for {symbol} from FMP"
                    + (f" (url: {self.last_url})" if self.last_url else "")
                )
                return None

            # Standardize column names
            # FMP typically returns: asset, name, marketValue, weight, sharesNumber, etc.
            column_mapping = {
                "asset": "Symbol",
                "name": "Name",
                "weight": "Weight",
                "weightPercentage": "Weight",
                "sharesNumber": "Shares",
                "marketValue": "Market_Value",
            }

            for old_col, new_col in column_mapping.items():
                if old_col in df.columns and new_col not in df.columns:
                    df.rename(columns={old_col: new_col}, inplace=True)

            # Convert weight to decimal proportion if present
            if "Weight" in df.columns:
                df["Weight"] = self._normalise_weights(df["Weight"])

            print(
                f"Successfully fetched {len(df)} holdings for {symbol} from FMP"
                + (f" via {used_endpoint}" if used_endpoint else "")
            )
            return df

        except Exception as e:
            url_info = f" (url: {self.last_url})" if self.last_url else ""
            print(f"Error fetching FMP data for {symbol}: {e}{url_info}")
            return None

    def get_etf_country_weights(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Return country allocation breakdown for an ETF.
        
        Note: May require premium FMP subscription. Returns None if unavailable.
        """
        params = {"symbol": symbol.upper()}
        data, _ = self._request_with_fallbacks(
            [
                "/api/v3/etf-country-weighting",
                "/api/v4/etf-country-weighting",
            ],
            params,
        )
        if not data:
            # Silently return None - this is optional data
            return None

        if not isinstance(data, list):
            print(
                f"Unexpected country allocation format for {symbol} from FMP"
                + (f" (url: {self.last_url})" if self.last_url else "")
            )
            return None

        df = pd.DataFrame(data)
        if df.empty:
            return None

        column_mapping = {
            "country": "Country",
            "countryName": "Country",
            "weight": "Weight",
            "weightPercentage": "Weight",
        }
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns and new_col not in df.columns:
                df.rename(columns={old_col: new_col}, inplace=True)

        if "Weight" in df.columns:
            df["Weight"] = self._normalise_weights(df["Weight"])

        return df

    def get_etf_sector_weights(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Return sector allocation breakdown for an ETF.
        
        Note: May require premium FMP subscription. Returns None if unavailable.
        """
        params = {"symbol": symbol.upper()}
        data, _ = self._request_with_fallbacks(
            [
                "/api/v3/etf-sector-weighting",
                "/api/v4/etf-sector-weighting",
            ],
            params,
        )

        if not data:
            # Silently return None - this is optional data
            return None

        if not isinstance(data, list):
            print(
                f"Unexpected sector allocation format for {symbol} from FMP"
                + (f" (url: {self.last_url})" if self.last_url else "")
            )
            return None

        df = pd.DataFrame(data)
        if df.empty:
            return None

        column_mapping = {
            "sector": "Sector",
            "name": "Sector",
            "weight": "Weight",
            "weightPercentage": "Weight",
        }
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns and new_col not in df.columns:
                df.rename(columns={old_col: new_col}, inplace=True)

        if "Weight" in df.columns:
            df["Weight"] = self._normalise_weights(df["Weight"])

        return df

    def get_etf_asset_allocation(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Return asset allocation (equity/bonds/cash) for an ETF.
        
        Note: May require premium FMP subscription. Returns None if unavailable.
        """
        params = {"symbol": symbol.upper()}
        data, _ = self._request_with_fallbacks(
            [
                "/api/v3/etf-stock-exposure",
                "/api/v4/etf-stock-exposure",
            ],
            params,
        )

        if not data:
            # Silently return None - this is optional data
            return None

        if not isinstance(data, list):
            print(
                f"Unexpected asset allocation format for {symbol} from FMP"
                + (f" (url: {self.last_url})" if self.last_url else "")
            )
            return None

        df = pd.DataFrame(data)
        if df.empty:
            return None

        column_mapping = {
            "asset": "Asset_Class",
            "type": "Asset_Class",
            "name": "Asset_Class",
            "weight": "Weight",
            "weightPercentage": "Weight",
        }
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns and new_col not in df.columns:
                df.rename(columns={old_col: new_col}, inplace=True)

        if "Weight" in df.columns:
            df["Weight"] = self._normalise_weights(df["Weight"])

        return df

    def get_etf_overview(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch ETF metadata such as category, issuer, expense ratio.
        
        Note: ETF profile endpoints may require premium FMP subscription.
        Falls back gracefully if not available.
        """
        try:
            params = {"symbol": symbol.upper()}
            # Try profile endpoint (may require premium)
            data, _ = self._request_with_fallbacks(
                [
                    "/api/v3/etf-info",
                    "/api/v4/etf-info",
                ],
                params,
            )

            if not data:
                # Silently return None - this is optional metadata
                return None

            if isinstance(data, list):
                record = data[0] if data else None
            elif isinstance(data, dict):
                record = data
            else:
                record = None

            if not record:
                return None

            return {
                "symbol": record.get("symbol") or record.get("etfSymbol"),
                "name": record.get("name") or record.get("companyName"),
                "category": record.get("category") or record.get("focus"),
                "issuer": record.get("issuer") or record.get("fundFamily"),
                "expense_ratio": record.get("expenseRatio") or record.get("expenseRatioAnnual"),
                "inception_date": record.get("inceptionDate"),
                "aum": record.get("assetsUnderManagement") or record.get("totalAssets"),
                "description": record.get("description"),
            }

        except Exception:
            # Silently fail - overview is optional metadata
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
            endpoint = "/stable/quote"
            params = {"symbol": symbol.upper()}
            data = self._make_request(endpoint, params)

            if not data or not isinstance(data, list) or len(data) == 0:
                print(
                    f"No quote data for {symbol} from FMP"
                    + (f" (url: {self.last_url})" if self.last_url else "")
                )
                return None

            quote = data[0]
            return {
                "symbol": quote.get("symbol"),
                "price": float(quote.get("price", 0)),
                "change": float(quote.get("change", 0)),
                "change_percent": quote.get("changesPercentage", 0),
                "volume": int(quote.get("volume", 0)),
            }
        except Exception as e:
            url_info = f" (url: {self.last_url})" if self.last_url else ""
            print(f"Error fetching quote for {symbol}: {e}{url_info}")
            return None

    def get_company_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get company profile including sector, industry, and fundamental data.

        Args:
            symbol: Stock ticker symbol.

        Returns:
            Dictionary with company data or None if unavailable.
        """
        try:
            endpoint = "/stable/profile"
            params = {"symbol": symbol.upper()}
            data = self._make_request(endpoint, params)

            if not data or not isinstance(data, list) or len(data) == 0:
                print(
                    f"No company profile for {symbol} from FMP"
                    + (f" (url: {self.last_url})" if self.last_url else "")
                )
                return None

            profile = data[0]
            return {
                "symbol": profile.get("symbol"),
                "name": profile.get("companyName"),
                "sector": profile.get("sector"),
                "industry": profile.get("industry"),
                "market_cap": profile.get("mktCap"),
                "price": profile.get("price"),
                "beta": profile.get("beta"),
                "website": profile.get("website"),
            }
        except Exception as e:
            url_info = f" (url: {self.last_url})" if self.last_url else ""
            print(f"Error fetching company profile for {symbol}: {e}{url_info}")
            return None

