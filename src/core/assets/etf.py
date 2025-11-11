"""
ETF asset class with FMP and AlphaVantage integration.
"""

from typing import Dict, Optional, List
import pandas as pd
import yfinance as yf
from .base import Asset

# Conditional imports for API clients
try:
    from api.fmp import FMPClient
    from api.alpha_vantage import AlphaVantageClient
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from api.fmp import FMPClient
    from api.alpha_vantage import AlphaVantageClient


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
        use_fmp: bool = True,
        use_alpha_vantage: bool = True,
    ):
        """
        Initialize an ETF.

        Args:
            ticker: ETF ticker symbol.
            units: Number of shares held.
            weight: Portfolio weight as decimal.
            use_fmp: Whether to use FMP for holdings data (tried first).
            use_alpha_vantage: Whether to use AlphaVantage for holdings data (tried after FMP).
        """
        super().__init__(ticker, units, weight)
        self._yf_ticker: Optional[yf.Ticker] = None
        self._use_fmp = use_fmp
        self._use_alpha_vantage = use_alpha_vantage
        self._fmp_client: Optional[FMPClient] = None
        self._av_client: Optional[AlphaVantageClient] = None
        self._is_excluded_type = False
        self._country_allocation: Optional[pd.DataFrame] = None
        self._sector_allocation: Optional[pd.DataFrame] = None
        self._asset_allocation: Optional[pd.DataFrame] = None
        self._fmp_overview: Optional[Dict[str, object]] = None

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

            # Store ETF-specific metadata
            self._metadata = {
                "category": info.get("category"),
                "total_assets": info.get("totalAssets"),
                "yield": info.get("yield"),
                "ytd_return": info.get("ytdReturn"),
                "expense_ratio": info.get("annualReportExpenseRatio"),
                "inception_date": info.get("fundInceptionDate"),
            }

            # Supplement with FMP overview data if available
            if self._use_fmp:
                fmp_overview = self.get_fmp_overview()
                if fmp_overview:
                    self._fmp_overview = fmp_overview
                    category = fmp_overview.get("category")
                    if category and (not self._sector or self._sector == "ETF"):
                        self._sector = category
                    self._metadata.update(
                        {
                            "issuer": fmp_overview.get("issuer")
                            or self._metadata.get("issuer"),
                            "expense_ratio": fmp_overview.get("expense_ratio")
                            or self._metadata.get("expense_ratio"),
                            "inception_date": fmp_overview.get("inception_date")
                            or self._metadata.get("inception_date"),
                            "total_assets": fmp_overview.get("aum")
                            or self._metadata.get("total_assets"),
                            "description": fmp_overview.get("description"),
                        }
                    )

            return self._price is not None

        except Exception as e:
            print(f"Error fetching data for ETF {self.ticker}: {e}")
            return False

    def get_holdings(self, max_holdings: int = 15) -> Optional[pd.DataFrame]:
        """
        Get underlying holdings of the ETF.

        Tries data sources in order: FMP API -> AlphaVantage API -> Yahoo Finance.

        Args:
            max_holdings: Maximum number of holdings to return.

        Returns:
            DataFrame with holdings data or None if unavailable.
        """
        # Skip holdings lookup for money market and bond funds
        if self._is_excluded_type:
            return None

        # Try FMP first
        if self._use_fmp:
            holdings_df = self._get_holdings_fmp(max_holdings)
            if holdings_df is not None:
                return holdings_df

        # Try AlphaVantage second
        if self._use_alpha_vantage:
            holdings_df = self._get_holdings_alpha_vantage(max_holdings)
            if holdings_df is not None:
                return holdings_df

        # Fallback to Yahoo Finance
        return self._get_holdings_yfinance(max_holdings)

    def get_country_allocation(self) -> Optional[pd.DataFrame]:
        """Get country allocation via FMP."""
        if not self._use_fmp:
            return None

        if self._country_allocation is not None:
            return self._country_allocation.copy()

        try:
            if self._fmp_client is None:
                self._fmp_client = FMPClient()
            country_df = self._fmp_client.get_etf_country_weights(self.ticker)
            if country_df is not None and not country_df.empty:
                self._country_allocation = country_df
                return country_df.copy()
        except ValueError as exc:
            print(f"FMP country allocation error for {self.ticker}: {exc}")
        except Exception as exc:
            print(f"Error fetching FMP country allocation for {self.ticker}: {exc}")

        return None

    def get_sector_allocation(self) -> Optional[pd.DataFrame]:
        """Get sector allocation via FMP."""
        if not self._use_fmp:
            return None

        if self._sector_allocation is not None:
            return self._sector_allocation.copy()

        try:
            if self._fmp_client is None:
                self._fmp_client = FMPClient()
            sector_df = self._fmp_client.get_etf_sector_weights(self.ticker)
            if sector_df is not None and not sector_df.empty:
                self._sector_allocation = sector_df
                return sector_df.copy()
        except ValueError as exc:
            print(f"FMP sector allocation error for {self.ticker}: {exc}")
        except Exception as exc:
            print(f"Error fetching FMP sector allocation for {self.ticker}: {exc}")

        return None

    def get_asset_allocation(self) -> Optional[pd.DataFrame]:
        """Get asset class allocation via FMP."""
        if not self._use_fmp:
            return None

        if self._asset_allocation is not None:
            return self._asset_allocation.copy()

        try:
            if self._fmp_client is None:
                self._fmp_client = FMPClient()
            allocation_df = self._fmp_client.get_etf_asset_allocation(self.ticker)
            if allocation_df is not None and not allocation_df.empty:
                self._asset_allocation = allocation_df
                return allocation_df.copy()
        except ValueError as exc:
            print(f"FMP asset allocation error for {self.ticker}: {exc}")
        except Exception as exc:
            print(f"Error fetching FMP asset allocation for {self.ticker}: {exc}")

        return None

    def get_fmp_overview(self) -> Optional[Dict[str, object]]:
        """Get ETF overview/metadata from FMP."""
        if not self._use_fmp:
            return None

        if self._fmp_overview is not None:
            return self._fmp_overview

        try:
            if self._fmp_client is None:
                self._fmp_client = FMPClient()
            overview = self._fmp_client.get_etf_overview(self.ticker)
            if overview:
                self._fmp_overview = overview
                return overview
        except ValueError as exc:
            print(f"FMP overview error for {self.ticker}: {exc}")
        except Exception as exc:
            print(f"Error fetching FMP overview for {self.ticker}: {exc}")

        return None

    def _get_holdings_fmp(self, max_holdings: int) -> Optional[pd.DataFrame]:
        """
        Get holdings from Financial Modeling Prep API.

        Args:
            max_holdings: Maximum number of holdings to return.

        Returns:
            DataFrame with holdings or None if unavailable.
        """
        try:
            if self._fmp_client is None:
                self._fmp_client = FMPClient()

            holdings_df = self._fmp_client.get_etf_holdings(self.ticker)

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
            print(f"FMP error for {self.ticker}: {e}")
            return None
        except Exception as e:
            print(f"Error fetching FMP holdings for {self.ticker}: {e}")
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

