"""
Stock asset class.
"""

from typing import Optional
import pandas as pd
import yfinance as yf
from .base import Asset


class Stock(Asset):
    """Represents a single stock holding."""

    def __init__(self, ticker: str, units: float = 0, weight: Optional[float] = None):
        """
        Initialize a stock.

        Args:
            ticker: Stock ticker symbol.
            units: Number of shares held.
            weight: Portfolio weight as decimal.
        """
        super().__init__(ticker, units, weight)
        self._yf_ticker: Optional[yf.Ticker] = None

    def fetch_data(self) -> bool:
        """
        Fetch live market data from Yahoo Finance.

        Returns:
            True if data fetch succeeded, False otherwise.
        """
        try:
            self._yf_ticker = yf.Ticker(self.ticker)
            
            # Try fast_info first for price
            try:
                self._price = self._yf_ticker.fast_info.get("lastPrice")
            except Exception:
                self._price = None

            # Fallback to info if fast_info failed
            if self._price is None:
                info = self._yf_ticker.info
                self._price = info.get("currentPrice") or info.get("regularMarketPrice")

            # Get sector and name
            info = self._yf_ticker.info
            self._sector = info.get("sector", "Unknown")
            self._name = info.get("longName") or info.get("shortName", self.ticker)
            
            # Store additional metadata
            self._metadata = {
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "dividend_yield": info.get("dividendYield"),
            }

            return self._price is not None

        except Exception as e:
            print(f"Error fetching data for stock {self.ticker}: {e}")
            return False

    def get_holdings(self, max_holdings: int = 15) -> Optional[pd.DataFrame]:
        """
        Stocks don't have underlying holdings.

        Returns:
            None (stocks are atomic holdings).
        """
        return None

    def get_fundamentals(self) -> dict:
        """
        Get fundamental data for the stock.

        Returns:
            Dictionary with fundamental metrics.
        """
        if self._yf_ticker is None:
            self.fetch_data()

        try:
            info = self._yf_ticker.info
            return {
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "price_to_book": info.get("priceToBook"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
            }
        except Exception as e:
            print(f"Error fetching fundamentals for {self.ticker}: {e}")
            return {}

