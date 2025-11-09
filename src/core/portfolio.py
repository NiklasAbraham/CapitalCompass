"""
Portfolio Composition Analysis Module

This module contains functions related to analyzing the user's
personal portfolio as defined in portfolio.json.
"""

import json
import os
from typing import Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

from config import PORTFOLIO_FILE


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
) -> Tuple[Optional[go.Figure], Optional[go.Figure]]:
    """
    Analyzes the composition of a portfolio defined in a JSON file.

    Fetches live data, calculates market values and weights, and
    returns two Plotly Figure objects for asset and sector allocation.

    Raises:
        FileNotFoundError: If the portfolio.json file is not found.

    Returns:
        A tuple (fig_asset, fig_sector):
        - fig_asset: Plotly Pie chart for asset allocation.
        - fig_sector: Plotly Pie chart for sector allocation (stocks only).
    """

    try:
        with open(filepath, "r") as f:
            portfolio = json.load(f)
    except FileNotFoundError:
        print(f"Error: {filepath} not found.")
        raise
    except json.JSONDecodeError:
        print(f"Error: Could not decode {filepath}. Check JSON format.")
        return None, None

    if not portfolio:
        print("Portfolio file is empty.")
        return None, None

    holdings_data = []
    total_portfolio_value = 0.0

    print("Fetching live market data for portfolio...")
    for item in portfolio:
        ticker_str = item.get("ticker")
        units = item.get("units", 0.0)

        if not ticker_str or units <= 0:
            continue

        try:
            ticker_obj = yf.Ticker(ticker_str)
            price = ticker_obj.fast_info["lastPrice"]
            market_value = units * price
            total_portfolio_value += market_value

            sector = "ETF / Other"
            if item.get("type") == "stock":
                sector = ticker_obj.info.get("sector", "Stock (No Sector)")

            holdings_data.append(
                {
                    "Ticker": ticker_str,
                    "Units": units,
                    "Price": price,
                    "Market_Value": market_value,
                    "Sector": sector,
                }
            )

        except Exception as e:
            print(f"Warning: Could not fetch data for {ticker_str}: {e}")

    if not holdings_data:
        print("No valid holdings data fetched.")
        return None, None

    print(f"Total Portfolio Value: ${total_portfolio_value:,.2f}")

    # Create DataFrame for analysis
    df = pd.DataFrame(holdings_data)
    df["Weight"] = df["Market_Value"] / total_portfolio_value

    # --- Visualization 1: Asset Allocation ---
    fig_asset = go.Figure(
        data=[
            go.Pie(
                labels=df["Ticker"],
                values=df["Market_Value"],
                textinfo="label+percent",
                hoverinfo="label+value",
                hole=0.3,
            )
        ]
    )
    fig_asset.update_layout(
        title_text="Portfolio Asset Allocation (by Market Value)",
        annotations=[dict(text="Assets", x=0.5, y=0.5, font_size=20, showarrow=False)],
    )

    # --- Visualization 2: Sector Allocation (Stocks Only) ---
    fig_sector = None
    stock_df = df[~df["Sector"].str.contains("ETF")]
    if not stock_df.empty:
        sector_grouped = stock_df.groupby("Sector")["Market_Value"].sum().reset_index()

        fig_sector = go.Figure(
            data=[
                go.Pie(
                    labels=sector_grouped["Sector"],
                    values=sector_grouped["Market_Value"],
                    textinfo="label+percent",
                    hoverinfo="label+value",
                    hole=0.3,
                )
            ]
        )
        fig_sector.update_layout(
            title_text="Stock Holdings Sector Allocation (by Market Value)",
            annotations=[
                dict(text="Sectors", x=0.5, y=0.5, font_size=20, showarrow=False)
            ],
        )
    else:
        print("No stocks with sector data found; skipping sector plot.")

    return fig_asset, fig_sector
