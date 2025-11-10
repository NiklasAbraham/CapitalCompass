"""
Portfolio composition analysis using asset classes.
"""

import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib.pyplot as plt
import pandas as pd

from config import PORTFOLIO_FILE
from core.assets import ETF, Asset, Stock


class SavedPlot:
    """Wrapper for saved plot paths with display capability."""

    def __init__(self, path: str):
        self.path = path

    def show(self):
        """Display the plot in Jupyter or print path otherwise."""
        try:
            from IPython.display import Image, display

            display(Image(filename=self.path))
        except ImportError:
            print(f"Plot saved to: {self.path}")

    def __str__(self) -> str:
        return self.path


def load_portfolio_config(filepath: str) -> List[Asset]:
    """
    Load portfolio configuration and create Asset objects.

    Args:
        filepath: Path to portfolio JSON file.

    Returns:
        List of Asset objects (Stock or ETF instances).
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Portfolio file not found: {filepath}")

    with open(filepath, "r") as f:
        config = json.load(f)

    assets: List[Asset] = []

    for item in config:
        ticker = item["ticker"]
        asset_type = item.get("type", "stock").lower()
        units = item.get("units", 0)
        weight = item.get("weight") or item.get("percentage")

        if asset_type == "etf":
            asset = ETF(ticker=ticker, units=units, weight=weight)
        else:
            asset = Stock(ticker=ticker, units=units, weight=weight)

        assets.append(asset)

    return assets


def fetch_portfolio_data(assets: List[Asset]) -> pd.DataFrame:
    """
    Fetch market data for all assets in portfolio.

    Args:
        assets: List of Asset objects.

    Returns:
        DataFrame with portfolio holdings data.
    """
    print("Fetching live market data for portfolio...")

    holdings_data = []

    for asset in assets:
        success = asset.fetch_data()

        if success:
            holdings_data.append(
                {
                    "Ticker": asset.ticker,
                    "Type": asset.asset_type.upper(),
                    "Units": asset.units if asset.units > 0 else None,
                    "Weight": asset.weight,
                    "Price": asset.price,
                    "Market_Value": asset.market_value,
                    "Sector": asset.sector,
                    "Name": asset.name,
                }
            )
        else:
            print(f"Warning: Could not fetch data for {asset.ticker}")
            holdings_data.append(
                {
                    "Ticker": asset.ticker,
                    "Type": asset.asset_type.upper(),
                    "Units": asset.units if asset.units > 0 else None,
                    "Weight": asset.weight,
                    "Price": None,
                    "Market_Value": None,
                    "Sector": "Unknown",
                    "Name": asset.ticker,
                }
            )

    df = pd.DataFrame(holdings_data)

    # Handle weight-based vs units-based portfolios
    has_units = df["Units"].notna().any()
    has_weights = df["Weight"].notna().any()

    if has_weights and not has_units:
        # Weight-only portfolio: normalize weights and use notional value
        total_weight = df["Weight"].sum()
        if abs(total_weight - 1.0) > 0.01:
            print(f"Normalizing weights (sum={total_weight:.4f}) to 1.0")
            df["Weight"] = df["Weight"] / total_weight

        # Use notional $1 for visualization
        df["Market_Value"] = df["Weight"]
        total_value = 1.0
        print(
            "Portfolio defined by weights only. Using notional total value of 1.0 for allocation charts."
        )

    elif has_units:
        # Units-based portfolio: calculate market values
        total_value = df["Market_Value"].sum()
        df["Weight"] = df["Market_Value"] / total_value

    else:
        raise ValueError(
            "Portfolio must specify either 'units' or 'weight' for each holding."
        )

    return df


def analyze_portfolio_with_assets(
    assets: List[Asset],
    max_etf_holdings: int = 15,
) -> Tuple[Optional[SavedPlot], Optional[SavedPlot], pd.DataFrame, pd.DataFrame]:
    """
    Analyze portfolio composition with ETF look-through.

    Args:
        assets: List of Asset objects.
        max_etf_holdings: Maximum holdings to retrieve per ETF.

    Returns:
        Tuple of (asset_plot, sector_plot, holdings_df, lookthrough_df).
    """
    # Fetch portfolio data
    holdings_df = fetch_portfolio_data(assets)

    # Create output directory
    output_dir = Path(__file__).resolve().parent.parent.parent / "outputs"
    output_dir.mkdir(exist_ok=True)

    # Asset allocation plot
    asset_path = output_dir / "portfolio_asset_allocation.png"
    fig, ax = plt.subplots(figsize=(10, 7))

    wedges, texts, autotexts = ax.pie(
        holdings_df["Market_Value"],
        labels=holdings_df["Ticker"],
        autopct="%1.1f%%",
        startangle=90,
    )

    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontsize(10)

    ax.set_title("Portfolio Asset Allocation", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(asset_path, dpi=150)
    plt.close()

    # Sector allocation plot (only for stocks with valid sectors)
    sector_df = holdings_df[
        (holdings_df["Type"] == "STOCK") & (holdings_df["Sector"] != "Unknown")
    ]

    sector_plot = None
    if not sector_df.empty:
        sector_summary = sector_df.groupby("Sector")["Market_Value"].sum()

        sector_path = output_dir / "portfolio_sector_allocation.png"
        fig, ax = plt.subplots(figsize=(10, 7))

        wedges, texts, autotexts = ax.pie(
            sector_summary.values,
            labels=sector_summary.index,
            autopct="%1.1f%%",
            startangle=90,
        )

        for autotext in autotexts:
            autotext.set_color("white")
            autotext.set_fontsize(10)

        ax.set_title("Portfolio Sector Allocation", fontsize=14, fontweight="bold")
        plt.tight_layout()
        plt.savefig(sector_path, dpi=150)
        plt.close()

        sector_plot = SavedPlot(str(sector_path))

    # ETF look-through analysis
    lookthrough_data = []
    etfs_without_data = []

    for asset in assets:
        if isinstance(asset, ETF):
            holdings = asset.get_holdings(max_etf_holdings)

            if holdings is not None and not holdings.empty:
                # Calculate contribution of each underlying holding
                etf_weight = asset.weight or (
                    asset.market_value / holdings_df["Market_Value"].sum()
                )

                for _, row in holdings.iterrows():
                    symbol = row.get("Symbol")
                    weight = row.get("Weight", 0)
                    name = row.get("Name", symbol)

                    if symbol and weight:
                        contribution = etf_weight * weight
                        lookthrough_data.append(
                            {
                                "Ticker": symbol,
                                "Name": name,
                                "ETF_Source": asset.ticker,
                                "Weight_in_ETF": weight,
                                "Contribution_to_Portfolio": contribution,
                            }
                        )
            else:
                etfs_without_data.append(asset.ticker)

    # Create look-through DataFrame
    if lookthrough_data:
        lookthrough_df = pd.DataFrame(lookthrough_data)

        # Aggregate by ticker (same stock may appear in multiple ETFs)
        aggregated = (
            lookthrough_df.groupby("Ticker")
            .agg(
                {
                    "Name": "first",
                    "Contribution_to_Portfolio": "sum",
                    "ETF_Source": lambda s: ", ".join(sorted(set(filter(None, s)))),
                }
            )
            .reset_index()
        )

        # Add direct holdings (non-ETF assets)
        for asset in assets:
            if not isinstance(asset, ETF):
                direct_weight = asset.weight or (
                    asset.market_value / holdings_df["Market_Value"].sum()
                )
                aggregated = pd.concat(
                    [
                        aggregated,
                        pd.DataFrame(
                            [
                                {
                                    "Ticker": asset.ticker,
                                    "Name": asset.name or asset.ticker,
                                    "Contribution_to_Portfolio": direct_weight,
                                    "ETF_Source": "DIRECT",
                                }
                            ]
                        ),
                    ],
                    ignore_index=True,
                )

        # Sort by contribution
        aggregated = aggregated.sort_values(
            "Contribution_to_Portfolio", ascending=False
        )
        aggregated = aggregated.rename(
            columns={
                "Contribution_to_Portfolio": "Portfolio_Weight",
                "ETF_Source": "Sources",
            }
        )

        lookthrough_df = aggregated
    else:
        lookthrough_df = pd.DataFrame()

    if etfs_without_data:
        print(f"\nETF holdings data not available for: {', '.join(etfs_without_data)}")

    asset_plot = SavedPlot(str(asset_path))

    return asset_plot, sector_plot, holdings_df, lookthrough_df


def analyze_portfolio_composition(
    filepath: str = PORTFOLIO_FILE,
    max_etf_holdings: int = 15,
) -> Tuple[Optional[SavedPlot], Optional[SavedPlot], pd.DataFrame, pd.DataFrame]:
    """
    Main entry point for portfolio analysis.

    Args:
        filepath: Path to portfolio JSON configuration.
        max_etf_holdings: Maximum holdings to retrieve per ETF.

    Returns:
        Tuple of (asset_plot, sector_plot, holdings_df, lookthrough_df).
    """
    assets = load_portfolio_config(filepath)
    return analyze_portfolio_with_assets(assets, max_etf_holdings)
