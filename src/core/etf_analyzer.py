"""
ETF Holdings Analysis Module

This module provides functions to analyze ETF holdings and perform
look-through analysis to understand underlying exposure.
"""

from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf


def get_etf_holdings(ticker: str, max_holdings: int = 10) -> Optional[pd.DataFrame]:
    """
    Attempts to retrieve the top holdings of an ETF using yfinance.

    Note: yfinance ETF holdings data can be incomplete or unavailable.
    This function provides best-effort retrieval.

    Args:
        ticker: The ETF ticker symbol.
        max_holdings: Maximum number of holdings to return.

    Returns:
        A DataFrame with holdings data, or None if unavailable.
    """
    try:
        etf = yf.Ticker(ticker)

        # Try to get holdings data
        if hasattr(etf, "funds_data") and etf.funds_data:
            holdings = etf.funds_data.get("holdings", None)
            if holdings:
                df = pd.DataFrame(holdings[:max_holdings])
                return df

        # Alternative: Try using the .info attribute
        info = etf.info
        if "holdings" in info and info["holdings"]:
            df = pd.DataFrame(info["holdings"][:max_holdings])
            return df

        print(f"Holdings data not available for {ticker}")
        return None

    except Exception as e:
        print(f"Error retrieving holdings for {ticker}: {e}")
        return None


def analyze_portfolio_with_lookthrough(
    portfolio: List[Dict], max_etf_holdings: int = 10
) -> pd.DataFrame:
    """
    Analyzes a portfolio with ETF look-through to show underlying exposure.

    This provides a best-effort analysis of indirect holdings through ETFs.

    Args:
        portfolio: List of portfolio holdings as dicts with 'ticker', 'units', 'type'.
        max_etf_holdings: Maximum number of holdings to retrieve per ETF.

    Returns:
        A DataFrame with direct and indirect holdings information.
    """
    all_holdings = []

    for item in portfolio:
        ticker = item.get("ticker")
        units = item.get("units", 0)
        asset_type = item.get("type", "unknown")

        if not ticker or units <= 0:
            continue

        try:
            ticker_obj = yf.Ticker(ticker)
            price = ticker_obj.fast_info.get("lastPrice", 0)
            market_value = units * price

            if asset_type == "etf":
                # Try to get ETF holdings
                holdings_df = get_etf_holdings(ticker, max_etf_holdings)

                if holdings_df is not None and not holdings_df.empty:
                    # Process ETF holdings
                    for _, holding in holdings_df.iterrows():
                        holding_ticker = holding.get("symbol", "Unknown")
                        holding_weight = holding.get("holdingPercent", 0)

                        all_holdings.append(
                            {
                                "Source": f"{ticker} (ETF)",
                                "Ticker": holding_ticker,
                                "Type": "Indirect (ETF)",
                                "Weight_in_ETF": holding_weight,
                                "Exposure_Value": market_value * holding_weight,
                            }
                        )
                else:
                    # No holdings data available, treat as single entity
                    all_holdings.append(
                        {
                            "Source": ticker,
                            "Ticker": ticker,
                            "Type": "ETF (No Look-Through)",
                            "Weight_in_ETF": None,
                            "Exposure_Value": market_value,
                        }
                    )
            else:
                # Direct stock holding
                all_holdings.append(
                    {
                        "Source": ticker,
                        "Ticker": ticker,
                        "Type": "Direct Stock",
                        "Weight_in_ETF": None,
                        "Exposure_Value": market_value,
                    }
                )

        except Exception as e:
            print(f"Error processing {ticker}: {e}")

    if not all_holdings:
        return pd.DataFrame()

    df = pd.DataFrame(all_holdings)

    # Aggregate by ticker to show total exposure
    total_exposure = df["Exposure_Value"].sum()
    aggregated = df.groupby("Ticker")["Exposure_Value"].sum().reset_index()
    aggregated["Portfolio_Weight"] = aggregated["Exposure_Value"] / total_exposure
    aggregated = aggregated.sort_values("Portfolio_Weight", ascending=False)

    return aggregated


def get_etf_info(ticker: str) -> Dict:
    """
    Retrieves comprehensive information about an ETF.

    Args:
        ticker: The ETF ticker symbol.

    Returns:
        A dictionary with ETF information.
    """
    try:
        etf = yf.Ticker(ticker)
        info = etf.info

        etf_data = {
            "Name": info.get("longName", "N/A"),
            "Category": info.get("category", "N/A"),
            "Total_Assets": info.get("totalAssets", "N/A"),
            "Expense_Ratio": info.get("annualReportExpenseRatio", "N/A"),
            "YTD_Return": info.get("ytdReturn", "N/A"),
            "Three_Year_Return": info.get("threeYearAverageReturn", "N/A"),
            "Five_Year_Return": info.get("fiveYearAverageReturn", "N/A"),
        }

        return etf_data

    except Exception as e:
        print(f"Error retrieving ETF info for {ticker}: {e}")
        return {}
