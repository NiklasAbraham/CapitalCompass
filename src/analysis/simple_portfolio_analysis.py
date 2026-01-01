"""
Simple Portfolio Analysis using Asset Classes

Provides current portfolio overview with ETF look-through using AlphaVantage API.
"""

import logging
import sys
import time
from pathlib import Path
from typing import Dict

import pandas as pd

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

try:
    from config import PORTFOLIO_FILE
    from core.portfolio import analyze_portfolio_composition, load_portfolio_config
except ModuleNotFoundError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from config import PORTFOLIO_FILE
    from core.portfolio import analyze_portfolio_composition, load_portfolio_config
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent


def format_percentage(value: float) -> str:
    """Format a decimal as percentage string."""
    return f"{value * 100:.2f}%"


def format_currency(value: float) -> str:
    """Format a value as currency string."""
    return f"${value:,.2f}"


def run_simple_portfolio_analysis(
    config_path: str = PORTFOLIO_FILE,
    max_etf_holdings: int = 15,
    holdings_source: str = "primary",
) -> Dict[str, object]:
    """
    Run portfolio analysis and display results.

    Args:
        config_path: Path to portfolio configuration JSON.
        max_etf_holdings: Maximum holdings to retrieve per ETF.
        holdings_source: Holdings backend to use for ETF look-through
            (``"primary"``, ``"auto"``, ``"alpha_vantage"``, or ``"yahoo"``).

    Returns:
        Dictionary with analysis results.
    """
    start_time = time.time()
    logger.info(f"Starting portfolio analysis with config: {config_path}")
    logger.info(f"Holdings source: {holdings_source}, Max holdings: {max_etf_holdings}")
    
    # Resolve config path relative to project root
    if not Path(config_path).is_absolute():
        config_path = str(PROJECT_ROOT / config_path)
    
    logger.info(f"Loading portfolio configuration from: {config_path}")
    load_start = time.time()
    assets = load_portfolio_config(
        config_path, holdings_source_override=holdings_source
    )
    logger.info(f"Loaded {len(assets)} assets in {time.time() - load_start:.2f}s")

    print("=" * 50)
    print("Current Portfolio Configuration:")
    print("=" * 50)
    print(f"ETF holdings source: {holdings_source.upper()}")

    for asset in assets:
        if asset.weight is not None:
            print(
                f"{asset.ticker:<8} - {asset.weight:>7.4f} weight ({asset.asset_type})"
            )
        else:
            print(f"{asset.ticker:<8} - {asset.units:>7.2f} units ({asset.asset_type})")

    print("=" * 50)

    # Run analysis
    logger.info("Starting portfolio composition analysis...")
    analysis_start = time.time()
    asset_plot, sector_plot, holdings_df, lookthrough_df = (
        analyze_portfolio_composition(
            filepath=config_path,
            max_etf_holdings=max_etf_holdings,
            holdings_source_override=holdings_source,
        )
    )
    logger.info(f"Portfolio analysis completed in {time.time() - analysis_start:.2f}s")

    # Display asset allocation plot
    if asset_plot:
        print(f"\nAsset allocation chart saved to: {asset_plot.path}")

    # Display sector allocation plot
    if sector_plot:
        print(f"Sector allocation chart saved to: {sector_plot.path}")

    # Display holdings overview
    print("\nHoldings Overview:")
    display_df = holdings_df[["Ticker", "Type", "Weight"]].copy()
    display_df["Weight"] = display_df["Weight"].apply(
        lambda x: f"{x * 100:.4f}" if pd.notna(x) else "N/A"
    )
    display_df.rename(columns={"Weight": "Weight (%)"}, inplace=True)
    print(display_df.to_string(index=False))

    # Display look-through analysis
    if not lookthrough_df.empty:
        print("\nTotal Exposure (Direct + Indirect via ETFs):")
        print("=" * 70)

        display_lookthrough = lookthrough_df.copy()
        display_lookthrough["Exposure_Value"] = display_lookthrough[
            "Portfolio_Weight"
        ].apply(format_currency)
        display_lookthrough["Portfolio_Weight"] = display_lookthrough[
            "Portfolio_Weight"
        ].apply(format_percentage)

        columns_to_show = ["Ticker", "Sources", "Exposure_Value", "Portfolio_Weight"]
        missing_cols = [
            col for col in columns_to_show if col not in display_lookthrough.columns
        ]
        for col in missing_cols:
            display_lookthrough[col] = "-"

        print(display_lookthrough[columns_to_show].to_string(index=False))

    # Display ETF exposure summaries (country / sector / asset allocation)
    exposures = holdings_df.attrs.get("etf_exposures", {})
    exposure_labels = {
        "country": ("ETF Country Allocation (Portfolio Level)", "Country"),
        "sector": ("ETF Sector Allocation (Portfolio Level)", "Sector"),
        "asset_class": ("ETF Asset-Class Allocation (Portfolio Level)", "Asset_Class"),
    }

    for key, (title, column_name) in exposure_labels.items():
        exposure_data = exposures.get(key, {})
        aggregated_df = exposure_data.get("aggregated")

        if aggregated_df is not None and not aggregated_df.empty:
            print(f"\n{title}:")
            display_df = aggregated_df.copy()
            display_df["Portfolio_Weight"] = display_df["Portfolio_Weight"].apply(
                format_percentage
            )
            columns = [column_name, "Portfolio_Weight", "ETF_Sources"]
            for col in columns:
                if col not in display_df.columns:
                    display_df[col] = "-"
            print(display_df[columns].to_string(index=False))

        missing_sources = exposure_data.get("missing") or []
        if missing_sources:
            print(
                f"  -> Missing {column_name.lower()} allocation data for: {', '.join(sorted(set(missing_sources)))}"
            )

    # Display ETF details
    etf_details = []
    for asset in assets:
        if asset.asset_type == "etf":
            metrics = (
                asset.get_performance_metrics()
                if hasattr(asset, "get_performance_metrics")
                else {}
            )
            etf_details.append(
                {
                    "Ticker": asset.ticker,
                    "Name": asset.name or "N/A",
                    "Category": metrics.get("category", "N/A"),
                    "Total Assets": metrics.get("total_assets", "N/A"),
                    "Expense Ratio": metrics.get("expense_ratio", "N/A"),
                    "YTD Return": metrics.get("ytd_return", "N/A"),
                    "3Y Return": metrics.get("3y_return", "N/A"),
                    "5Y Return": metrics.get("5y_return", "N/A"),
                }
            )

    if etf_details:
        print("\nETF Details:")
        etf_df = pd.DataFrame(etf_details)
        print(etf_df.to_string(index=False))

    total_time = time.time() - start_time
    logger.info(f"Total analysis time: {total_time:.2f}s")
    
    return {
        "holdings": holdings_df,
        "lookthrough": lookthrough_df,
        "asset_plot": asset_plot,
        "sector_plot": sector_plot,
        "exposures": exposures,
    }


if __name__ == "__main__":
    # Example: Run with default config
    run_simple_portfolio_analysis(
        config_path="config_Niklas.json",
        max_etf_holdings=15,
    )

    print("\n" + "=" * 70)
    print("Analysis complete!")
    print("=" * 70)
