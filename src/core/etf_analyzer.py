"""
ETF Holdings Analysis Module

This module provides functions to analyze ETF holdings and perform
look-through analysis to understand underlying exposure.
"""

from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf


def _standardise_holdings_frame(
    df: pd.DataFrame, max_holdings: int
) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None

    df = df.head(max_holdings).copy()

    # Normalise weight column
    if "holdingPercent" not in df.columns:
        for candidate in ("Holding Percent", "weight", "pct", "holding_percent"):
            if candidate in df.columns:
                df["holdingPercent"] = df[candidate]
                break
    if "holdingPercent" not in df.columns:
        return None

    # Normalise symbol column
    if "symbol" not in df.columns:
        if df.index.name and df.index.name.lower() in {"symbol", "ticker"}:
            df = df.reset_index().rename(columns={df.index.name: "symbol"})
        else:
            for candidate in ("Symbol", "symbol", "ticker", "holdingSymbol", "name"):
                if candidate in df.columns:
                    df["symbol"] = df[candidate]
                    break

    if "symbol" not in df.columns:
        return None

    return df[["symbol", "holdingPercent"]].dropna()


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

        # Attempt via fund_holdings DataFrame
        df_candidate = getattr(etf, "fund_holdings", None)
        df_candidate = _standardise_holdings_frame(df_candidate, max_holdings)
        if df_candidate is not None and not df_candidate.empty:
            return df_candidate

        # Attempt via funds_data attribute
        funds_data = getattr(etf, "funds_data", None)
        holdings = None
        if funds_data is not None:
            # Newer yfinance exposes top_holdings DataFrame
            top_holdings = getattr(funds_data, "top_holdings", None)
            if hasattr(top_holdings, "reset_index"):
                df_candidate = _standardise_holdings_frame(
                    top_holdings.reset_index(), max_holdings
                )
                if df_candidate is not None and not df_candidate.empty:
                    return df_candidate

            holdings = getattr(funds_data, "holdings", None)
            if holdings is None and isinstance(funds_data, dict):
                holdings = funds_data.get("holdings")
        if holdings:
            df_candidate = _standardise_holdings_frame(
                pd.DataFrame(holdings), max_holdings
            )
            if df_candidate is not None and not df_candidate.empty:
                return df_candidate

        # Alternative: Try using the .info attribute
        info = etf.info
        if isinstance(info, dict) and info.get("holdings"):
            df_candidate = _standardise_holdings_frame(pd.DataFrame(info["holdings"]), max_holdings)
            if df_candidate is not None and not df_candidate.empty:
                return df_candidate

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
    missing_holdings: List[str] = []

    for item in portfolio:
        ticker = item.get("ticker")
        units = float(item.get("units", 0))
        market_value = item.get("market_value")
        asset_type = item.get("type", "unknown")

        if not ticker:
            continue

        try:
            ticker_obj = yf.Ticker(ticker)
            price = ticker_obj.fast_info.get("lastPrice", 0)
            if market_value is None:
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
                    missing_holdings.append(ticker)
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

    if missing_holdings:
        print(
            "ETF holdings data not available for: "
            + ", ".join(sorted(set(missing_holdings)))
        )

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
