"""
Market Simulation Module

This module contains functions for the quantitative simulation of
the S&P 500 index, including data scraping and backtesting.
"""

from typing import List, Optional

import pandas as pd
import plotly.graph_objects as go
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from config import SP500_WIKI_URL


def get_sp500_tickers() -> List[str]:
    """
    Scrapes the Wikipedia page for S&P 500 constituents to get a list of tickers.
    Handles common ticker symbol corrections (e.g., BRK.B -> BRK-B).

    Returns:
        A list of S&P 500 ticker symbols.
    """
    print("Fetching S&P 500 constituent list from Wikipedia...")
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(SP500_WIKI_URL, headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses

        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", {"id": "constituents"})

        if table is None:
            raise ValueError(
                "Could not find the 'constituents' table on the Wikipedia page."
            )

        # Use pandas.read_html on the string representation of the table
        # Requires 'lxml' to be installed (added to requirements.txt)
        df = pd.read_html(str(table))[0]

        tickers = df["Symbol"].tolist()

        # Yahoo Finance uses '-' for dots in tickers (e.g., BRK.B -> BRK-B)
        tickers = [t.replace(".", "-") for t in tickers]

        print(f"Successfully fetched {len(tickers)} S&P 500 tickers.")
        return tickers

    except Exception as e:
        print(f"Error scraping S&P 500 tickers: {e}")
        # Provide a minimal fallback list to allow partial functionality
        print("Warning: Using minimal fallback ticker list.")
        return ["AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "TSLA", "^GSPC"]


def analyze_index_exclusion(
    exclusion_list: List[str], start_date: str
) -> Optional[go.Figure]:
    """
    Performs a counterfactual simulation of the S&P 500.

    Compares three performance series and returns a Plotly Figure:
    1. The official S&P 500 Index (^GSPC)
    2. An equal-weighted simulation of all constituents
    3. An equal-weighted simulation excluding the provided list

    Args:
        exclusion_list: A list of ticker symbols to exclude from the simulation.
        start_date: The start date for the analysis (YYYY-MM-DD).

    Returns:
        A Plotly Figure object for the simulation, or None on failure.
    """

    sp500_tickers = get_sp500_tickers()
    benchmark_ticker = "^GSPC"

    # Ensure benchmark is in the download list
    if benchmark_ticker not in sp500_tickers:
        sp500_tickers.append(benchmark_ticker)

    # Tickers for the equal-weighted baseline (all stocks, no index)
    stock_tickers = [t for t in sp500_tickers if t != benchmark_ticker]

    print("Downloading historical price data... (This may take a moment)")
    try:
        data = yf.download(sp500_tickers, start=start_date)["Adj Close"]
        data = data.dropna(axis=1, how="all")  # Drop columns with no data
    except Exception as e:
        print(f"Error downloading historical data: {e}")
        return None

    # Calculate daily returns
    daily_returns = data.pct_change().dropna(how="all")

    # 1. Benchmark Returns (Official Index)
    if benchmark_ticker not in daily_returns.columns:
        print(f"Error: Benchmark ticker {benchmark_ticker} data not found.")
        return None
    benchmark_returns = daily_returns[benchmark_ticker]

    # 2. Baseline Simulation (Equal-Weighted S&P 500)
    # Ensure we only use tickers we successfully downloaded
    valid_stock_tickers = [t for t in stock_tickers if t in daily_returns.columns]
    baseline_returns = daily_returns[valid_stock_tickers].mean(axis=1)

    # 3. Modified Simulation (Equal-Weighted Ex-Exclusions)
    modified_tickers = [t for t in valid_stock_tickers if t not in exclusion_list]
    if not modified_tickers:
        print("Error: Exclusion list resulted in no tickers for modified simulation.")
        return None

    modified_returns = daily_returns[modified_tickers].mean(axis=1)

    print("Calculating cumulative performance...")
    # Calculate cumulative returns, fill NaNs to handle days with no returns
    cum_benchmark = (1 + benchmark_returns.fillna(0)).cumprod()
    cum_baseline = (1 + baseline_returns.fillna(0)).cumprod()
    cum_modified = (1 + modified_returns.fillna(0)).cumprod()

    # --- Visualization ---
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=cum_benchmark.index,
            y=cum_benchmark,
            name="S&P 500 Benchmark (^GSPC)",
            line=dict(color="black", width=3, dash="dash"),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=cum_baseline.index,
            y=cum_baseline,
            name="Equal-Weighted S&P 500 (Baseline)",
            line=dict(color="blue", width=2),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=cum_modified.index,
            y=cum_modified,
            name=f"Equal-Weighted (Ex-{len(exclusion_list)} Companies)",
            line=dict(color="red", width=2),
        )
    )

    fig.update_layout(
        title_text=f"S&P 500 Counterfactual Analysis (Since {start_date})",
        xaxis_title="Date",
        yaxis_title="Cumulative Performance (Normalized to 1)",
        hovermode="x unified",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )

    return fig
