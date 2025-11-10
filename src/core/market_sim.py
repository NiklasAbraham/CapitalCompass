"""
Market Simulation Module

This module contains functions for the quantitative simulation of
the S&P 500 index, including data scraping and backtesting.
"""

import os
from io import StringIO
from typing import Dict, List, Optional

import matplotlib.pyplot as plt
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from config import SP500_WIKI_URL

OUTPUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "outputs")
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _fetch_market_caps(tickers: List[str]) -> Dict[str, float]:
    """
    Retrieve current market capitalisations for the supplied tickers.

    Args:
        tickers: Symbols to query.

    Returns:
        Mapping of ticker -> market cap (only for tickers that returned a value).
    """

    market_caps: Dict[str, float] = {}

    # yfinance batching via Tickers is not fully reliable; loop with basic caching.
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            market_cap = info.get("marketCap")
            if market_cap and market_cap > 0:
                market_caps[ticker] = float(market_cap)
        except Exception:
            # Silently skip problematic tickers; they will fall back to equal weighting.
            continue

    return market_caps


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

        df = pd.read_html(StringIO(str(table)))[0]

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
    exclusion_list: List[str],
    start_date: str,
    use_market_caps: bool = True,
) -> Optional[str]:
    """
    Performs a counterfactual simulation of the S&P 500.

    Compares three performance series and returns a plot path:
    1. The official S&P 500 Index (^GSPC)
    2. A simulated index of all constituents (market-cap weighted by default)
    3. The same simulation excluding the provided list

    Args:
        exclusion_list: A list of ticker symbols to exclude from the simulation.
        start_date: The start date for the analysis (YYYY-MM-DD).

    Returns:
        Path to the saved matplotlib plot, or None on failure.
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
        data = yf.download(
            sp500_tickers,
            start=start_date,
            auto_adjust=False,
            progress=True,
        )
        if isinstance(data.columns, pd.MultiIndex):
            data = data["Adj Close"]
        else:
            data = data.to_frame(name=sp500_tickers[0])
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

    valid_stock_tickers = [t for t in stock_tickers if t in daily_returns.columns]

    weights_baseline = pd.Series(1.0, index=valid_stock_tickers)
    if use_market_caps:
        print("Applying current market-cap weights...")
        market_caps = _fetch_market_caps(valid_stock_tickers)
        if market_caps:
            weights_baseline = pd.Series(market_caps)
            weights_baseline = weights_baseline[weights_baseline > 0]
        else:
            print("Warning: Market-cap data unavailable; reverting to equal weighting.")

    if weights_baseline.empty:
        print("Error: No usable market-cap data; aborting simulation.")
        return None

    weights_baseline = weights_baseline / weights_baseline.sum()
    common_cols = daily_returns.columns.intersection(weights_baseline.index)
    baseline_returns = daily_returns[common_cols].mul(
        weights_baseline.loc[common_cols], axis=1
    ).sum(axis=1)

    modified_tickers = [t for t in weights_baseline.index if t not in exclusion_list]
    if not modified_tickers:
        print("Error: Exclusion list resulted in no tickers for modified simulation.")
        return None

    weights_modified = weights_baseline.loc[modified_tickers]
    weights_modified = weights_modified / weights_modified.sum()
    modified_returns = daily_returns[weights_modified.index].mul(
        weights_modified, axis=1
    ).sum(axis=1)

    print("Calculating cumulative performance...")
    # Calculate cumulative returns, fill NaNs to handle days with no returns
    cum_benchmark = (1 + benchmark_returns.fillna(0)).cumprod()
    cum_baseline = (1 + baseline_returns.fillna(0)).cumprod()
    cum_modified = (1 + modified_returns.fillna(0)).cumprod()

    # --- Visualization ---
    label_baseline = (
        "Market-Cap Weighted S&P 500 (Baseline)"
        if use_market_caps
        else "Equal-Weighted S&P 500 (Baseline)"
    )
    label_modified = (
        f"Market-Cap Weighted (Ex-{len(exclusion_list)} Companies)"
        if use_market_caps
        else f"Equal-Weighted (Ex-{len(exclusion_list)} Companies)"
    )

    plt.figure(figsize=(10, 6))
    plt.plot(cum_benchmark.index, cum_benchmark.values, label="S&P 500 Benchmark (^GSPC)", linewidth=2, linestyle="--", color="black")
    plt.plot(cum_baseline.index, cum_baseline.values, label=label_baseline, linewidth=2, color="blue")
    plt.plot(
        cum_modified.index,
        cum_modified.values,
        label=label_modified,
        linewidth=2,
        color="red",
    )
    plt.title(f"S&P 500 Counterfactual Analysis (Since {start_date})")
    plt.xlabel("Date")
    plt.ylabel("Cumulative Performance (Normalized to 1)")
    plt.legend(loc="best")
    plt.grid(alpha=0.3)
    plt.tight_layout()

    output_path = os.path.join(
        OUTPUT_DIR, f"index_exclusion_{start_date.replace('-', '')}.png"
    )
    plt.savefig(output_path, dpi=150)
    plt.close()

    return output_path
