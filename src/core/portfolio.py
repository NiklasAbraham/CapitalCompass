"""
Portfolio composition analysis using asset classes.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


def _portfolio_signature(assets: List[Asset]) -> str:
    """Create a stable signature for a portfolio configuration."""
    serialisable = []
    for asset in sorted(assets, key=lambda a: (a.asset_type, a.ticker)):
        serialisable.append(
            {
                "ticker": asset.ticker,
                "type": asset.asset_type,
                "units": asset.units,
                "weight": asset.weight,
            }
        )
    raw = json.dumps(serialisable, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_portfolio_config(
    filepath: str,
    holdings_source_override: Optional[str] = None,
) -> List[Asset]:
    """
    Load portfolio configuration and create Asset objects.

    Args:
        filepath: Path to portfolio JSON file.
        holdings_source_override: Optional override for ETF holdings source
            (``"primary"``, ``"auto"``, ``"alpha_vantage"``, or ``"yahoo"``).

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
            holdings_source = (
                item.get("holdings_source")
                or holdings_source_override
                or "auto"
            )
            asset = ETF(
                ticker=ticker,
                units=units,
                weight=weight,
                holdings_source=holdings_source,
            )
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

    # ETF look-through analysis with optional caching
    is_weight_only = holdings_df["Units"].isna().all()
    cache_dir = output_dir / "cache"
    cache_dir.mkdir(exist_ok=True)
    cache_file: Optional[Path] = None
    lookthrough_df: Optional[pd.DataFrame] = None
    exposures: Dict[str, Dict[str, pd.DataFrame]] = {}
    etfs_without_data: List[str] = []
    etf_holdings_records: Dict[str, Dict[str, object]] = {}

    if is_weight_only:
        signature = _portfolio_signature(assets)
        cache_file = cache_dir / f"lookthrough_{signature}.csv"
        if cache_file.exists():
            try:
                cached = pd.read_csv(cache_file)
                if not cached.empty:
                    cached["Portfolio_Weight"] = pd.to_numeric(
                        cached.get("Portfolio_Weight"), errors="coerce"
                    )
                    lookthrough_df = cached
                    print(f"Loaded cached ETF look-through from {cache_file}")
            except Exception as exc:
                print(f"Failed to load cached look-through ({exc}); recomputing...")
                lookthrough_df = None

    if lookthrough_df is None:
        lookthrough_data = []

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

                    full_snapshot = asset.get_full_holdings()
                    if full_snapshot is None or full_snapshot.empty:
                        full_snapshot = holdings

                    if full_snapshot is not None and not full_snapshot.empty:
                        etf_holdings_records[asset.ticker] = {
                            "data": full_snapshot.copy(),
                            "metadata": asset.get_holdings_metadata(),
                        }
                else:
                    etfs_without_data.append(asset.ticker)

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

            if cache_file and not lookthrough_df.empty:
                try:
                    lookthrough_df.to_csv(cache_file, index=False)
                    print(f"Saved ETF look-through cache to {cache_file}")
                except Exception as exc:
                    print(f"Failed to write look-through cache ({exc})")
        else:
            lookthrough_df = pd.DataFrame()
    else:
        etfs_without_data = []

    # Ensure we capture holdings snapshots even when look-through is loaded from cache
    for asset in assets:
        if not isinstance(asset, ETF):
            continue
        if asset.ticker in etf_holdings_records:
            continue

        snapshot_df = asset.get_full_holdings()
        if snapshot_df is None or snapshot_df.empty:
            snapshot_df = asset.get_holdings(max_etf_holdings)
        if snapshot_df is not None and not snapshot_df.empty:
            etf_holdings_records[asset.ticker] = {
                "data": snapshot_df.copy(),
                "metadata": asset.get_holdings_metadata(),
            }

    if etfs_without_data:
        print(f"\nETF holdings data not available for: {', '.join(etfs_without_data)}")

    # Compute ETF exposure summaries (country/sector/asset allocation)
    exposure_results = _compute_etf_exposures(
        assets=assets,
        holdings_df=holdings_df,
        output_dir=output_dir,
        cache_dir=cache_dir if is_weight_only else None,
        portfolio_signature=signature if is_weight_only else None,
    )
    exposures.update(exposure_results)

    # Persist ETF holdings snapshots (including timestamp metadata)
    holdings_output_dir = output_dir / "etf_holdings"
    holdings_output_dir.mkdir(exist_ok=True)
    saved_holdings_info: Dict[str, Dict[str, object]] = {}

    for ticker, payload in etf_holdings_records.items():
        snapshot_df = payload.get("data")
        if snapshot_df is None or snapshot_df.empty:
            continue

        metadata = dict(payload.get("metadata") or {})
        enriched_df = snapshot_df.copy()

        as_of = metadata.get("as_of")
        if as_of:
            enriched_df["Holdings_As_Of"] = as_of

        source = metadata.get("source")
        if source:
            enriched_df["Holdings_Source"] = source

        fetched_at = metadata.get("fetched_at")
        if fetched_at:
            enriched_df["Holdings_Fetched_At"] = fetched_at

        output_path = holdings_output_dir / f"{ticker}_holdings.csv"

        try:
            enriched_df.to_csv(output_path, index=False)
        except Exception as exc:
            print(f"Failed to write holdings snapshot for {ticker} ({exc})")
            continue

        saved_holdings_info[ticker] = {
            "path": str(output_path),
            "metadata": metadata,
            "data": enriched_df,
        }

    if saved_holdings_info:
        holdings_df.attrs["etf_holdings"] = saved_holdings_info

    holdings_df.attrs["etf_exposures"] = exposures

    asset_plot = SavedPlot(str(asset_path))

    return asset_plot, sector_plot, holdings_df, lookthrough_df


def analyze_portfolio_composition(
    filepath: str = PORTFOLIO_FILE,
    max_etf_holdings: int = 15,
    holdings_source_override: Optional[str] = None,
) -> Tuple[Optional[SavedPlot], Optional[SavedPlot], pd.DataFrame, pd.DataFrame]:
    """
    Main entry point for portfolio analysis.

    Args:
        filepath: Path to portfolio JSON configuration.
        max_etf_holdings: Maximum holdings to retrieve per ETF.
        holdings_source_override: Override holdings source for ETFs
            (``"primary"``, ``"auto"``, ``"alpha_vantage"``, or ``"yahoo"``).

    Returns:
        Tuple of (asset_plot, sector_plot, holdings_df, lookthrough_df).
    """
    assets = load_portfolio_config(
        filepath, holdings_source_override=holdings_source_override
    )
    return analyze_portfolio_with_assets(assets, max_etf_holdings)


def _compute_etf_exposures(
    assets: List[Asset],
    holdings_df: pd.DataFrame,
    output_dir: Path,
    cache_dir: Optional[Path] = None,
    portfolio_signature: Optional[str] = None,
) -> Dict[str, Dict[str, pd.DataFrame]]:
    """
    Compute aggregated ETF exposure tables (country, sector, asset allocation).

    Args:
        assets: List of portfolio assets.
        holdings_df: Holdings DataFrame with normalized weights.
        output_dir: Directory to write exposure CSV summaries.
        cache_dir: Directory for cached exposures (weight-based portfolios).
        portfolio_signature: Stable portfolio signature for cache file naming.

    Returns:
        Dictionary mapping exposure type to aggregated/detail DataFrames.
    """

    def _load_cached_exposure(
        exposure_type: str,
    ) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        if not cache_dir or not portfolio_signature:
            return None, None

        summary_path = cache_dir / f"{exposure_type}_exposure_{portfolio_signature}.csv"
        detail_path = cache_dir / f"{exposure_type}_exposure_detail_{portfolio_signature}.csv"
        summary_df = None
        detail_df = None

        try:
            if summary_path.exists():
                summary_df = pd.read_csv(summary_path)
            if detail_path.exists():
                detail_df = pd.read_csv(detail_path)
        except Exception as exc:
            print(f"Failed to load cached {exposure_type} exposure ({exc}); recomputing...")
            summary_df = None
            detail_df = None

        return summary_df, detail_df

    def _save_cached_exposure(
        exposure_type: str,
        summary_df: pd.DataFrame,
        detail_df: pd.DataFrame,
    ) -> None:
        if not cache_dir or not portfolio_signature:
            return

        summary_path = cache_dir / f"{exposure_type}_exposure_{portfolio_signature}.csv"
        detail_path = cache_dir / f"{exposure_type}_exposure_detail_{portfolio_signature}.csv"
        try:
            summary_df.to_csv(summary_path, index=False)
            if not detail_df.empty:
                detail_df.to_csv(detail_path, index=False)
        except Exception as exc:
            print(f"Failed to cache {exposure_type} exposure ({exc})")

    def _compute_single_exposure(
        label: str,
        fetcher,
        column_name: str,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
        records: List[Dict[str, object]] = []
        missing_sources: List[str] = []
        weight_lookup = holdings_df.set_index("Ticker")["Weight"].to_dict()

        for asset in assets:
            if not isinstance(asset, ETF):
                continue

            etf_weight = weight_lookup.get(asset.ticker)
            if etf_weight is None or pd.isna(etf_weight) or etf_weight == 0:
                continue

            exposure_df = fetcher(asset)
            if exposure_df is None or exposure_df.empty:
                missing_sources.append(asset.ticker)
                continue

            for _, row in exposure_df.iterrows():
                label_value = row.get(column_name)
                weight_value = row.get("Weight")

                if label_value is None or (isinstance(label_value, float) and pd.isna(label_value)):
                    continue

                try:
                    weight_float = float(weight_value)
                except (TypeError, ValueError):
                    continue

                if pd.isna(weight_float):
                    continue

                contribution = etf_weight * weight_float
                if contribution == 0:
                    continue

                records.append(
                    {
                        column_name: label_value,
                        "ETF_Source": asset.ticker,
                        "Weight_in_ETF": weight_float,
                        "Portfolio_Weight": contribution,
                    }
                )

        if records:
            detail_df = pd.DataFrame(records)
            aggregated_df = (
                detail_df.groupby(column_name)
                .agg(
                    {
                        "Portfolio_Weight": "sum",
                        "ETF_Source": lambda s: ", ".join(sorted(set(filter(None, s)))),
                    }
                )
                .reset_index()
                .rename(columns={"ETF_Source": "ETF_Sources"})
                .sort_values("Portfolio_Weight", ascending=False)
            )
        else:
            aggregated_df = pd.DataFrame(
                columns=[column_name, "Portfolio_Weight", "ETF_Sources"]
            )
            detail_df = pd.DataFrame(
                columns=[column_name, "ETF_Source", "Weight_in_ETF", "Portfolio_Weight"]
            )

        return aggregated_df, detail_df, missing_sources

    exposure_configs = [
        ("country", lambda etf: etf.get_country_allocation(), "Country"),
        ("sector", lambda etf: etf.get_sector_allocation(), "Sector"),
        ("asset_class", lambda etf: etf.get_asset_allocation(), "Asset_Class"),
    ]

    exposure_results: Dict[str, Dict[str, pd.DataFrame]] = {}

    for exposure_key, fetcher, column_name in exposure_configs:
        cached_summary, cached_detail = _load_cached_exposure(exposure_key)

        if cached_summary is not None:
            summary_df = cached_summary
            detail_df = cached_detail if cached_detail is not None else pd.DataFrame(
                columns=[column_name, "ETF_Source", "Weight_in_ETF", "Portfolio_Weight"]
            )
            missing_sources: List[str] = []
        else:
            summary_df, detail_df, missing_sources = _compute_single_exposure(
                label=exposure_key,
                fetcher=fetcher,
                column_name=column_name,
            )
            if not summary_df.empty:
                _save_cached_exposure(exposure_key, summary_df, detail_df)

        exposure_results[exposure_key] = {
            "aggregated": summary_df,
            "detail": detail_df,
            "missing": missing_sources,
        }

        # Persist latest exposure snapshot to outputs for user inspection
        summary_filename = f"portfolio_{exposure_key}_exposure.csv"
        detail_filename = f"portfolio_{exposure_key}_exposure_detail.csv"
        try:
            summary_df.to_csv(output_dir / summary_filename, index=False)
            if not detail_df.empty:
                detail_df.to_csv(output_dir / detail_filename, index=False)
        except Exception as exc:
            print(f"Failed to write {exposure_key} exposure CSV ({exc})")

        if missing_sources:
            print(
                f"{column_name} allocation data not available for: {', '.join(sorted(set(missing_sources)))}"
            )

    return exposure_results
