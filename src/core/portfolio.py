"""
Portfolio Composition Analysis Module

This module contains functions related to analyzing the user's
personal portfolio as defined in portfolio.json.
"""

import json
import os
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

from config import PORTFOLIO_FILE
from core.etf_analyzer import analyze_portfolio_with_lookthrough

OUTPUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "outputs")
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


class SavedPlot:
    """
    Lightweight wrapper around a saved chart file, providing a `show()` method for
    interactive environments (e.g., Jupyter notebooks).
    """

    def __init__(self, path: str):
        self.path = path

    def show(self):
        if not self.path or not os.path.exists(self.path):
            print("Plot not available.")
            return

        try:
            from IPython.display import Image, display  # type: ignore

            display(Image(filename=self.path))
        except Exception:
            print(f"Plot saved to: {self.path}")

    def __repr__(self):
        return f"SavedPlot(path='{self.path}')"


def create_dummy_portfolio(filepath: str = PORTFOLIO_FILE):
    """
    Creates a dummy portfolio.json file if one does not exist.
    This provides a template for the user.
    """
    if not os.path.exists(filepath):
        print(f"Creating dummy {filepath} as a template...")
        dummy_data = [
            {"ticker": "AAPL", "units": 10, "type": "stock"},
            {"ticker": "MSFT", "units": 15, "type": "stock"},
            {"ticker": "VOO", "units": 50, "type": "etf"},
            {"ticker": "NVDA", "units": 5, "type": "stock"},
        ]
        with open(filepath, "w") as f:
            json.dump(dummy_data, f, indent=4)


def analyze_portfolio_composition(
    filepath: str = PORTFOLIO_FILE,
    lookup_etf_holdings: bool = False,
    max_etf_holdings: int = 15,
) -> Tuple[Optional[SavedPlot], Optional[SavedPlot], Optional[pd.DataFrame]]:
    """
    Analyzes the composition of a portfolio defined in a JSON file.

    Fetches live data, calculates market values and weights, and
    returns two Plotly Figure objects for asset and sector allocation.

    Raises:
        FileNotFoundError: If the portfolio.json file is not found.

    Returns:
        asset_plot, sector_plot, etf_lookthrough_df (only when lookup_etf_holdings=True)
    """

    try:
        with open(filepath, "r") as f:
            portfolio = json.load(f)
    except FileNotFoundError:
        print(f"Error: {filepath} not found.")
        raise
    except json.JSONDecodeError:
        print(f"Error: Could not decode {filepath}. Check JSON format.")
        return None, None, None

    if not portfolio:
        print("Portfolio file is empty.")
        return None, None, None

    entries = []
    has_units = False
    has_weights = False

    print("Fetching live market data for portfolio...")
    for item in portfolio:
        ticker_str = item.get("ticker")
        if not ticker_str:
            continue

        units = item.get("units")
        weight_input = item.get("weight")
        if weight_input is None:
            weight_input = item.get("percentage")

        try:
            ticker_obj = yf.Ticker(ticker_str)
            price = ticker_obj.fast_info.get("lastPrice", float("nan"))
            sector = "ETF / Other"
            if item.get("type") == "stock":
                sector = ticker_obj.info.get("sector", "Stock (No Sector)")
        except Exception as e:
            print(f"Warning: Could not fetch data for {ticker_str}: {e}")
            price = float("nan")
            sector = "Unknown"

        if units is not None and units > 0:
            has_units = True
            entries.append(
                {
                    "Ticker": ticker_str,
                    "Units": units,
                    "Price": price,
                    "Sector": sector,
                    "mode": "units",
                }
            )
        elif weight_input is not None:
            has_weights = True
            try:
                weight_value = float(weight_input)
            except (TypeError, ValueError):
                print(f"Warning: Invalid weight value for {ticker_str}; skipping.")
                continue
            entries.append(
                {
                    "Ticker": ticker_str,
                    "Units": None,
                    "Price": price,
                    "Sector": sector,
                    "mode": "weights",
                    "weight_input": weight_value,
                }
            )
        else:
            print(f"Warning: {ticker_str} has neither units nor weight; skipping.")

    if not entries:
        print("No valid holdings data fetched.")
        return None, None

    if has_units and has_weights:
        print(
            "Error: Mixing absolute units and percentage weights in the same "
            "portfolio is not supported. Please choose one approach."
        )
        return None, None

    holdings_data = []
    total_portfolio_value = 0.0

    if has_units:
        for entry in entries:
            market_value = entry["Units"] * entry["Price"]
            total_portfolio_value += market_value
            holdings_data.append(
                {
                    "Ticker": entry["Ticker"],
                    "Units": entry["Units"],
                    "Price": entry["Price"],
                    "Market_Value": market_value,
                    "Sector": entry["Sector"],
                }
            )
        print(f"Total Portfolio Value: ${total_portfolio_value:,.2f}")
    else:
        weights_raw = [abs(e["weight_input"]) for e in entries]
        total_raw = sum(weights_raw)
        if total_raw == 0:
            print("Error: Weight entries sum to zero.")
            return None, None, None
            return None, None, None

        # If weights look like percentages (e.g., sum approx 100), convert to fraction.
        if total_raw > 1.5:
            weights_raw = [w / 100.0 for w in weights_raw]
            total_raw = sum(weights_raw)

        weights_normalised = [w / total_raw for w in weights_raw]
        total_portfolio_value = 1.0  # Notional total
        print(
            "Portfolio defined by weights only. Using notional total value of 1.0 "
            "for allocation charts."
        )

        for entry, weight in zip(entries, weights_normalised):
            market_value = weight * total_portfolio_value
            holdings_data.append(
                {
                    "Ticker": entry["Ticker"],
                    "Units": None,
                    "Price": entry["Price"],
                    "Market_Value": market_value,
                    "Sector": entry["Sector"],
                }
            )

    # Create DataFrame for analysis
    df = pd.DataFrame(holdings_data)
    df["Weight"] = df["Market_Value"] / total_portfolio_value

    # --- Visualization 1: Asset Allocation ---
    asset_path = os.path.join(OUTPUT_DIR, "portfolio_asset_allocation.png")
    plt.figure(figsize=(6, 6))
    plt.pie(
        df["Market_Value"],
        labels=df["Ticker"],
        autopct="%1.1f%%",
        startangle=90,
    )
    plt.title("Portfolio Asset Allocation (by Market Value)")
    plt.tight_layout()
    plt.savefig(asset_path, dpi=150)
    plt.close()

    # --- Visualization 2: Sector Allocation (Stocks Only) ---
    sector_path: Optional[str] = None
    stock_df = df[~df["Sector"].str.contains("ETF")]
    if not stock_df.empty:
        sector_grouped = stock_df.groupby("Sector")["Market_Value"].sum().reset_index()

        sector_path = os.path.join(OUTPUT_DIR, "portfolio_sector_allocation.png")
        plt.figure(figsize=(6, 6))
        plt.pie(
            sector_grouped["Market_Value"],
            labels=sector_grouped["Sector"],
            autopct="%1.1f%%",
            startangle=90,
        )
        plt.title("Stock Holdings Sector Allocation (by Market Value)")
        plt.tight_layout()
        plt.savefig(sector_path, dpi=150)
        plt.close()
    else:
        print("No stocks with sector data found; skipping sector plot.")

    asset_plot = SavedPlot(asset_path) if asset_path else None
    sector_plot = SavedPlot(sector_path) if sector_path else None

    lookthrough_df: Optional[pd.DataFrame] = None
    if lookup_etf_holdings:
        lookthrough_df = analyze_portfolio_with_lookthrough(
            [
                {
                    "ticker": row["Ticker"],
                    "units": row["Units"] if row["Units"] is not None else 0,
                    "type": "etf" if "ETF" in row["Sector"] else "stock",
                    "market_value": row["Market_Value"],
                }
                for row in holdings_data
            ],
            max_etf_holdings=max_etf_holdings,
        )

    return asset_plot, sector_plot, lookthrough_df
