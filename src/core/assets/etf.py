"""
ETF asset class with issuer/SEC pipeline and AlphaVantage integration.
"""

from typing import Dict, Optional

import pandas as pd
import yfinance as yf

from .base import Asset

# Conditional import for AlphaVantage client
try:
    from api.alpha_vantage import AlphaVantageClient
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from api.alpha_vantage import AlphaVantageClient

try:  # Local primary holdings pipeline (optional)
    from pipeline import PrimaryHoldingsClient, PrimaryHoldingsError
except ImportError:  # pragma: no cover - optional dependency path
    PrimaryHoldingsClient = None  # type: ignore
    PrimaryHoldingsError = Exception  # type: ignore


class ETF(Asset):
    """Represents an ETF holding with look-through capability."""

    # Keywords indicating money market or bond funds that don't need holdings lookup
    EXCLUSION_KEYWORDS = [
        "money",
        "cash",
        "treasury",
        "bond",
        "govt",
        "government",
        "term",
        "ibonds",
    ]

    def __init__(
        self,
        ticker: str,
        units: float = 0,
        weight: Optional[float] = None,
        use_alpha_vantage: bool = True,
        holdings_source: str = "auto",
        primary_holdings_client: Optional["PrimaryHoldingsClient"] = None,
    ):
        """
        Initialize an ETF.

        Args:
            ticker: ETF ticker symbol.
            units: Number of shares held.
            weight: Portfolio weight as decimal.
            use_alpha_vantage: Whether to use AlphaVantage for holdings data (fallback).
            holdings_source: Preferred holdings source: ``"auto"`` (default),
                ``"primary"`` to use only the issuer/SEC pipeline, ``"alpha_vantage"``
                to skip the pipeline, or ``"yahoo"`` for Yahoo Finance only. The
                legacy value ``"fmp"`` is treated as ``"auto"`` for backwards
                compatibility.
            primary_holdings_client: Optional injected pipeline client (primarily for testing).
        """
        super().__init__(ticker, units, weight)
        self._yf_ticker: Optional[yf.Ticker] = None
        normalized_source = (holdings_source or "auto").lower()
        if normalized_source == "fmp":
            normalized_source = "auto"
        if normalized_source not in {"auto", "primary", "alpha_vantage", "yahoo"}:
            normalized_source = "auto"
        self._holdings_source = normalized_source
        self._use_alpha_vantage = use_alpha_vantage or self._holdings_source == "alpha_vantage"
        self._require_holdings = self._holdings_source == "primary"
        self._av_client: Optional[AlphaVantageClient] = None
        self._is_excluded_type = False
        self._country_allocation: Optional[pd.DataFrame] = None
        self._sector_allocation: Optional[pd.DataFrame] = None
        self._asset_allocation: Optional[pd.DataFrame] = None
        self._primary_client: Optional["PrimaryHoldingsClient"] = primary_holdings_client
        self._primary_holdings_full: Optional[pd.DataFrame] = None
        self._primary_metadata: Optional[Dict[str, object]] = None
        self._primary_error: Optional[str] = None

    def fetch_data(self) -> bool:
        """
        Fetch live market data from Yahoo Finance.

        Returns:
            True if data fetch succeeded, False otherwise.
        """
        try:
            self._yf_ticker = yf.Ticker(self.ticker)

            # Get price
            try:
                self._price = self._yf_ticker.fast_info.get("lastPrice")
            except Exception:
                self._price = None

            if self._price is None:
                info = self._yf_ticker.info
                self._price = info.get("currentPrice") or info.get(
                    "regularMarketPrice"
                ) or info.get("navPrice")

            # Get ETF metadata
            info = self._yf_ticker.info
            self._name = info.get("longName") or info.get("shortName", self.ticker)
            self._sector = info.get("category", "ETF")

            # Check if this is an excluded type (bonds, money market, etc.)
            name_lower = (self._name or "").lower()
            category_lower = (self._sector or "").lower()
            self._is_excluded_type = any(
                keyword in name_lower or keyword in category_lower
                for keyword in self.EXCLUSION_KEYWORDS
            )

            if self._require_holdings:
                self._is_excluded_type = False

            # Store ETF-specific metadata
            self._metadata = {
                "category": info.get("category"),
                "total_assets": info.get("totalAssets"),
                "yield": info.get("yield"),
                "ytd_return": info.get("ytdReturn"),
                "expense_ratio": info.get("annualReportExpenseRatio"),
                "inception_date": info.get("fundInceptionDate"),
            }

            return self._price is not None

        except Exception as e:
            print(f"Error fetching data for ETF {self.ticker}: {e}")
            return False

    def get_holdings(self, max_holdings: int = 15) -> Optional[pd.DataFrame]:
        """Get underlying holdings of the ETF."""
        # Skip holdings lookup for money market and bond funds
        if self._is_excluded_type:
            return None

        # Try the primary pipeline first when requested
        if self._holdings_source in {"primary", "auto"}:
            holdings_df = self._get_holdings_primary(max_holdings)
            if holdings_df is not None:
                return holdings_df
            if self._holdings_source == "primary":
                return None

        # Try AlphaVantage next
        if self._holdings_source in {"alpha_vantage", "auto"} and self._use_alpha_vantage:
            holdings_df = self._get_holdings_alpha_vantage(max_holdings)
            if holdings_df is not None:
                return holdings_df
            if self._holdings_source == "alpha_vantage":
                return self._get_holdings_yfinance(max_holdings)

        if self._holdings_source == "yahoo":
            return self._get_holdings_yfinance(max_holdings)

        # Fallback to Yahoo Finance
        return self._get_holdings_yfinance(max_holdings)

    def get_country_allocation(self) -> Optional[pd.DataFrame]:
        """Get country allocation using the configured data source."""
        if self._holdings_source in {"primary", "auto"}:
            allocations = self._get_primary_exposure("country")
            if allocations is not None:
                return allocations
            if self._holdings_source == "primary":
                return None

        return None

    def get_sector_allocation(self) -> Optional[pd.DataFrame]:
        """Get sector allocation using the configured data source."""
        if self._holdings_source in {"primary", "auto"}:
            allocations = self._get_primary_exposure("sector")
            if allocations is not None:
                return allocations
            if self._holdings_source == "primary":
                return None

        return None

    def get_asset_allocation(self) -> Optional[pd.DataFrame]:
        """Get asset class allocation using the configured data source."""
        if self._holdings_source in {"primary", "auto"}:
            allocations = self._get_primary_exposure("asset_class")
            if allocations is not None:
                return allocations
            if self._holdings_source == "primary":
                return None

        return None

    def _get_holdings_alpha_vantage(
        self, max_holdings: int
    ) -> Optional[pd.DataFrame]:
        """
        Get holdings from AlphaVantage API.

        Args:
            max_holdings: Maximum number of holdings to return.

        Returns:
            DataFrame with holdings or None if unavailable.
        """
        try:
            if self._av_client is None:
                self._av_client = AlphaVantageClient()

            holdings_df = self._av_client.get_etf_profile(self.ticker)
            
            if holdings_df is not None and not holdings_df.empty:
                # Limit to max holdings
                holdings_df = holdings_df.head(max_holdings)
                
                # Ensure we have required columns
                if "Symbol" not in holdings_df.columns:
                    holdings_df["Symbol"] = None
                if "Weight" not in holdings_df.columns:
                    holdings_df["Weight"] = None
                
                return holdings_df

            return None

        except ValueError as e:
            # API key issues or rate limits
            print(f"AlphaVantage error for {self.ticker}: {e}")
            return None
        except Exception as e:
            print(f"Error fetching AlphaVantage holdings for {self.ticker}: {e}")
            return None

    def _get_holdings_yfinance(self, max_holdings: int) -> Optional[pd.DataFrame]:
        """
        Get holdings from Yahoo Finance (fallback).

        Args:
            max_holdings: Maximum number of holdings to return.

        Returns:
            DataFrame with holdings or None if unavailable.
        """
        try:
            if self._yf_ticker is None:
                self._yf_ticker = yf.Ticker(self.ticker)

            print(f"Yahoo Finance fallback for {self.ticker} holdings")

            funds_data = getattr(self._yf_ticker, "funds_data", None)
            if funds_data is None:
                return None

            # Try top_holdings attribute
            holdings_df = getattr(funds_data, "top_holdings", None)
            if holdings_df is not None and not holdings_df.empty:
                holdings_df = holdings_df.reset_index()
                
                # Standardize column names
                column_mapping = {
                    "symbol": "Symbol",
                    "Symbol": "Symbol",
                    "holdingName": "Name",
                    "Name": "Name",
                    "holdingPercent": "Weight",
                    "Holding Percent": "Weight",
                }
                holdings_df.rename(columns=column_mapping, inplace=True)
                
                # Convert weight to decimal if needed
                if "Weight" in holdings_df.columns:
                    if holdings_df["Weight"].dtype == "object":
                        holdings_df["Weight"] = (
                            pd.to_numeric(
                                holdings_df["Weight"].str.rstrip("%"), errors="coerce"
                            )
                            / 100.0
                        )
                
                return holdings_df.head(max_holdings)

            return None

        except Exception as e:
            print(f"Error fetching Yahoo Finance holdings for {self.ticker}: {e}")
            return None

    # ------------------------------------------------------------------
    # Primary pipeline helpers
    # ------------------------------------------------------------------

    def _ensure_primary_client(self) -> Optional["PrimaryHoldingsClient"]:
        if self._primary_client is not None or PrimaryHoldingsClient is None:
            return self._primary_client

        try:
            self._primary_client = PrimaryHoldingsClient()
        except Exception as exc:  # pragma: no cover - defensive log
            self._primary_error = str(exc)
            print(f"Failed to initialise primary holdings client for {self.ticker}: {exc}")
            self._primary_client = None
        return self._primary_client

    def _ensure_primary_holdings(self) -> Optional[pd.DataFrame]:
        if self._primary_holdings_full is not None:
            return self._primary_holdings_full

        client = self._ensure_primary_client()
        if client is None:
            return None

        try:
            holdings_df, metadata = client.fetch_holdings(self.ticker)
        except PrimaryHoldingsError as exc:
            self._primary_error = str(exc)
            print(f"Primary holdings error for {self.ticker}: {exc}")
            return None

        if holdings_df is None or holdings_df.empty:
            return None

        self._primary_holdings_full = holdings_df
        self._primary_metadata = metadata
        self._metadata.setdefault("primary_holdings", {}).update(metadata)
        return self._primary_holdings_full

    def _get_holdings_primary(self, max_holdings: int) -> Optional[pd.DataFrame]:
        holdings_full = self._ensure_primary_holdings()
        if holdings_full is None:
            return None

        result = holdings_full.copy()
        if max_holdings:
            result = result.head(max_holdings).copy()
            total = result["Weight"].sum()
            if total and not pd.isna(total):
                result["Weight"] = result["Weight"] / total

        return result

    def _get_primary_exposure(self, dimension: str) -> Optional[pd.DataFrame]:
        holdings_full = self._ensure_primary_holdings()
        if holdings_full is None or holdings_full.empty:
            return None

        client = self._ensure_primary_client()
        if client is None:
            return None

        if dimension == "country":
            return client.get_country_exposure(holdings_full)
        if dimension == "sector":
            return client.get_sector_exposure(holdings_full)
        if dimension == "asset_class":
            return client.get_asset_class_exposure(holdings_full)
        return None

    def is_excluded_type(self) -> bool:
        """
        Check if this ETF is a money market or bond fund.

        Returns:
            True if this is an excluded type (no holdings lookup needed).
        """
        return self._is_excluded_type

    def get_performance_metrics(self) -> dict:
        """
        Get performance metrics for the ETF.

        Returns:
            Dictionary with performance data.
        """
        if self._yf_ticker is None:
            self.fetch_data()

        try:
            info = self._yf_ticker.info
            return {
                "ytd_return": info.get("ytdReturn"),
                "3y_return": info.get("threeYearAverageReturn"),
                "5y_return": info.get("fiveYearAverageReturn"),
                "expense_ratio": info.get("annualReportExpenseRatio"),
                "yield": info.get("yield"),
                "total_assets": info.get("totalAssets"),
            }
        except Exception as e:
            print(f"Error fetching performance metrics for {self.ticker}: {e}")
            return {}

