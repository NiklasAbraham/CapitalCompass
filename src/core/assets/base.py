"""
Base Asset class for all financial instruments.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import pandas as pd


class Asset(ABC):
    """Abstract base class for all asset types."""

    def __init__(self, ticker: str, units: float = 0, weight: Optional[float] = None):
        """
        Initialize an asset.

        Args:
            ticker: Ticker symbol.
            units: Number of units held (0 for weight-based portfolios).
            weight: Portfolio weight as decimal (e.g., 0.25 for 25%).
        """
        self.ticker = ticker
        self.units = units
        self.weight = weight
        self._price: Optional[float] = None
        self._sector: Optional[str] = None
        self._name: Optional[str] = None
        self._metadata: Dict[str, Any] = {}

    @abstractmethod
    def fetch_data(self) -> bool:
        """
        Fetch live market data for this asset.

        Returns:
            True if data fetch succeeded, False otherwise.
        """
        pass

    @abstractmethod
    def get_holdings(self, max_holdings: int = 15) -> Optional[pd.DataFrame]:
        """
        Get underlying holdings for this asset.

        For stocks, returns None.
        For ETFs, returns DataFrame of holdings.

        Args:
            max_holdings: Maximum number of holdings to return.

        Returns:
            DataFrame with holdings data or None.
        """
        pass

    @property
    def price(self) -> Optional[float]:
        """Current market price."""
        return self._price

    @property
    def sector(self) -> Optional[str]:
        """Asset sector or category."""
        return self._sector

    @property
    def name(self) -> Optional[str]:
        """Asset name."""
        return self._name

    @property
    def market_value(self) -> Optional[float]:
        """Market value of the holding (units * price)."""
        if self._price is not None and self.units is not None:
            return self.units * self._price
        return None

    @property
    def asset_type(self) -> str:
        """Type of asset (e.g., 'stock', 'etf')."""
        return self.__class__.__name__.lower()

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert asset to dictionary representation.

        Returns:
            Dictionary with asset attributes.
        """
        return {
            "ticker": self.ticker,
            "type": self.asset_type,
            "units": self.units,
            "weight": self.weight,
            "price": self.price,
            "market_value": self.market_value,
            "sector": self.sector,
            "name": self.name,
            "metadata": self._metadata,
        }

    def __repr__(self) -> str:
        if self.weight is not None:
            return f"{self.__class__.__name__}({self.ticker}, weight={self.weight:.2%})"
        return f"{self.__class__.__name__}({self.ticker}, units={self.units})"

