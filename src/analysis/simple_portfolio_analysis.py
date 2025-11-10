"""
Simple Portfolio Analysis Script
================================

"""

import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import PORTFOLIO_FILE  # noqa: E402
from core.etf_analyzer import (  # noqa: E402
    analyze_portfolio_with_lookthrough,
    get_etf_info,
)
from core.portfolio import analyze_portfolio_composition  # noqa: E402


def _resolve_config_path(config_path: str) -> Path:
    path = Path(config_path)
    if path.is_absolute():
        return path
    candidate = PROJECT_ROOT / path
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Portfolio configuration not found: {path}")


def _load_portfolio(config_path: str) -> List[Dict]:
    resolved = _resolve_config_path(config_path)
    with resolved.open("r") as f:
        return json.load(f)


def _print_portfolio_summary(portfolio: Iterable[Dict]) -> None:
    print("Current Portfolio Configuration:")
    print("=" * 50)
    for item in portfolio:
        ticker = item.get("ticker", "N/A")
        asset_type = item.get("type", "N/A")

        if "units" in item:
            label = "units"
            value = f"{item['units']:8.2f}"
        elif "weight" in item:
            label = "weight"
            value = f"{item['weight']:8.4f}"
        elif "percentage" in item:
            label = "percentage"
            value = f"{item['percentage']:8.2f}%"
        else:
            label = ""
            value = f"{'N/A':>8}"

        print(f"{ticker:8} - {value} {label} ({asset_type})")
    print("=" * 50)


def _build_holdings_table(
    portfolio: Iterable[Dict],
) -> Tuple[pd.DataFrame, List[Dict[str, object]]]:
    display_rows: List[Dict[str, object]] = []
    payload_rows: List[Dict[str, object]] = []
    weight_indices: List[int] = []
    raw_weights: List[float] = []

    for item in portfolio:
        ticker = item.get("ticker")
        if not ticker:
            continue

        try:
            data = yf.Ticker(ticker)
            price = data.fast_info.get("lastPrice", float("nan"))
        except Exception:
            price = float("nan")

        entry_display: Dict[str, object] = {
            "Ticker": ticker,
            "Type": item.get("type", "N/A").upper(),
        }
        entry_payload: Dict[str, object] = {
            "ticker": ticker,
            "type": item.get("type", "unknown"),
            "market_value": 0.0,
        }

        if "units" in item:
            units = float(item["units"])
            entry_display["Units"] = units
            notional = units * price if pd.notna(price) else units
            entry_payload["market_value"] = notional
        elif "weight" in item:
            raw_weight = float(item["weight"])
            entry_display["Weight_raw"] = raw_weight
            weight_indices.append(len(display_rows))
            raw_weights.append(raw_weight)
        elif "percentage" in item:
            raw_weight = float(item["percentage"]) / 100.0
            entry_display["Weight_raw"] = raw_weight
            weight_indices.append(len(display_rows))
            raw_weights.append(raw_weight)
        else:
            entry_display["Units"] = 0.0

        display_rows.append(entry_display)
        payload_rows.append(entry_payload)

    if weight_indices:
        total_weight = sum(raw_weights)
        if total_weight == 0:
            total_weight = 1.0
        for idx, raw_weight in zip(weight_indices, raw_weights):
            weight = raw_weight / total_weight
            display_rows[idx]["Weight"] = weight
            payload_rows[idx]["market_value"] = weight

    df_display = pd.DataFrame(display_rows)
    return df_display, payload_rows


def _print_holdings_table(df: pd.DataFrame) -> None:
    print("\nHoldings Overview:")
    printable = df.copy()
    if "Weight_raw" in printable.columns:
        printable.drop(columns=["Weight_raw"], inplace=True)
    if "Weight" in printable.columns:
        printable["Weight (%)"] = printable["Weight"] * 100
        printable.drop(columns=["Weight"], inplace=True)
    print(
        printable.to_string(
            index=False, na_rep="N/A", float_format=lambda x: f"{x:,.4f}"
        )
    )


def _print_lookthrough_table(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        print("\nETF holdings data not available for look-through analysis.")
        return

    display_df = df.copy()
    display_df["Exposure_Value"] = display_df["Exposure_Value"].map(
        lambda x: f"${x:,.2f}"
    )
    display_df["Portfolio_Weight"] = display_df["Portfolio_Weight"].map(
        lambda x: f"{x:.2%}"
    )

    print("\nTotal Exposure (Direct + Indirect via ETFs):")
    print("=" * 70)
    print(display_df.to_string(index=False))


def _print_etf_details(portfolio: Iterable[Dict]) -> None:
    etf_items = [item for item in portfolio if item.get("type", "").lower() == "etf"]

    for etf_item in etf_items:
        ticker = etf_item.get("ticker")
        if not ticker:
            continue

        print("\n" + "=" * 70)
        print(f"ETF: {ticker}")
        print("=" * 70)

        info = get_etf_info(ticker)
        if not info:
            print("No additional ETF information available.")
            continue

        for key, value in info.items():
            label = key.replace("_", " ").title()
            print(f"{label:.<30} {value}")


def run_simple_portfolio_analysis(
    config_path: str = PORTFOLIO_FILE,
    lookup_etf_holdings: bool = True,
    max_etf_holdings: int = 15,
) -> Dict[str, object]:
    """
    Executes the simplified portfolio analysis.

    Args:
        config_path: Path to the portfolio configuration file.
        lookup_etf_holdings: Whether to fetch ETF constituent data.
        max_etf_holdings: Number of holdings to request per ETF.

    Returns:
        Dictionary containing generated plots and data frames.
    """

    portfolio = _load_portfolio(config_path)
    _print_portfolio_summary(portfolio)

    asset_plot, sector_plot, lookthrough_df = analyze_portfolio_composition(
        filepath=str(_resolve_config_path(config_path)),
        lookup_etf_holdings=lookup_etf_holdings,
        max_etf_holdings=max_etf_holdings,
    )

    if asset_plot:
        print(f"Asset allocation chart saved to: {asset_plot.path}")
    if sector_plot:
        print(f"Sector allocation chart saved to: {sector_plot.path}")

    holdings_df, lookthrough_payload = _build_holdings_table(portfolio)
    _print_holdings_table(holdings_df)

    if lookup_etf_holdings:
        lookthrough_df = analyze_portfolio_with_lookthrough(
            lookthrough_payload, max_etf_holdings=max_etf_holdings
        )
        _print_lookthrough_table(lookthrough_df)

    _print_etf_details(portfolio)

    return {
        "asset_plot": asset_plot,
        "sector_plot": sector_plot,
        "holdings": holdings_df,
        "lookthrough": lookthrough_df,
    }


if __name__ == "__main__":
    run_simple_portfolio_analysis()
