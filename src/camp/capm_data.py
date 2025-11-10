"""
CAPM Data Utilities
===================

Helper functions to pull and prepare the data required for
Capital Asset Pricing Model (CAPM) based analytics and optimisation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import pandas as pd
import yfinance as yf

from config import DEFAULT_RISK_FREE_RATE


@dataclass
class CapmDataset:
    """
    Container for the core CAPM inputs.

    Attributes:
        asset_returns: Daily percentage returns for portfolio assets.
        benchmark_returns: Daily percentage returns for the benchmark index.
        risk_free_rate: Annual risk-free rate used for CAPM calculations.
    """

    asset_returns: pd.DataFrame
    benchmark_returns: pd.Series
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE

    def dropna(self) -> "CapmDataset":
        """
        Return a copy with rows containing NaNs removed
        (align asset and benchmark returns).
        """

        aligned = pd.concat(
            [self.asset_returns, self.benchmark_returns], axis=1
        ).dropna()
        asset_cols = self.asset_returns.columns
        benchmark_name = self.benchmark_returns.name
        return CapmDataset(
            asset_returns=aligned[asset_cols],
            benchmark_returns=aligned[benchmark_name],
            risk_free_rate=self.risk_free_rate,
        )


def fetch_price_data(
    tickers: Iterable[str],
    start_date: str,
    end_date: Optional[str] = None,
    adjust: bool = True,
) -> pd.DataFrame:
    """
    Download historical price series for the requested tickers using yfinance.

    Args:
        tickers: Iterable of ticker symbols.
        start_date: Start of historical window (YYYY-MM-DD).
        end_date: Optional end of window; defaults to latest available date.
        adjust: Whether to use adjusted close prices.

    Returns:
        Pandas DataFrame of prices indexed by date.
    """

    download = yf.download(
        tickers=list(tickers),
        start=start_date,
        end=end_date,
        progress=False,
        auto_adjust=adjust,
    )

    # yfinance returns different shapes for single vs multi tickers.
    if isinstance(download.columns, pd.MultiIndex):
        price_df = download["Adj Close" if adjust else "Close"].copy()
    else:
        price_df = download.rename("price").to_frame()

    return price_df.dropna(how="all")


def compute_returns(price_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert a price DataFrame to percentage returns.

    Args:
        price_df: Price series indexed by date.

    Returns:
        DataFrame of percentage returns (dropping the first NaN row).
    """

    return price_df.pct_change().dropna(how="all")


def prepare_capm_dataset(
    asset_tickers: Iterable[str],
    benchmark_ticker: str = "^GSPC",
    start_date: str = "2015-01-01",
    end_date: Optional[str] = None,
    risk_free_rate: float = DEFAULT_RISK_FREE_RATE,
) -> CapmDataset:
    """
    Pull and align asset + benchmark data ready for CAPM calculations.

    Args:
        asset_tickers: Collection of portfolio asset tickers.
        benchmark_ticker: Market benchmark (default S&P 500).
        start_date: Start of historical window.
        end_date: Optional end date.
        risk_free_rate: Annual risk-free rate to plug into CAPM.

    Returns:
        CapmDataset containing aligned return series.
    """

    asset_prices = fetch_price_data(asset_tickers, start_date, end_date)
    benchmark_prices = fetch_price_data([benchmark_ticker], start_date, end_date)

    asset_returns = compute_returns(asset_prices)
    benchmark_returns = compute_returns(benchmark_prices)[benchmark_ticker]

    dataset = CapmDataset(
        asset_returns=asset_returns,
        benchmark_returns=benchmark_returns,
        risk_free_rate=risk_free_rate,
    )

    return dataset.dropna()


__all__ = [
    "CapmDataset",
    "compute_returns",
    "fetch_price_data",
    "prepare_capm_dataset",
]

