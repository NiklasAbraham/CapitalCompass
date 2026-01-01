"""Automatic holdings snapshot generation for funds without local data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

try:
    import yfinance as yf  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    yf = None  # type: ignore


@dataclass
class AutoSnapshotResult:
    success: bool
    message: str


class AutoSnapshotManager:
    """Create gold holdings snapshots when none exist on disk."""

    def __init__(
        self,
        base_path: Path,
        registry: Dict[str, Dict[str, object]],
    ) -> None:
        self._base_path = base_path
        self._registry = registry
        # New simplified structure: data/funds/[fund_name]/[date]/
        project_root = (
            base_path.parent.parent
            if base_path.name == "pipeline"
            else base_path.parent
        )
        self._funds_dir = project_root / "data" / "funds"
        self._funds_dir.mkdir(parents=True, exist_ok=True)
        self._pipeline = None

    # ------------------------------------------------------------------ #
    def ensure_snapshot(
        self,
        entry: Dict[str, object],
        as_of_override: Optional[str],
    ) -> AutoSnapshotResult:
        """Ensure a gold snapshot exists for the given fund entry."""
        import logging

        logger = logging.getLogger(__name__)

        fund_id = entry.get("fund_id")
        if not isinstance(fund_id, str):
            logger.warning("[AutoSnapshot] Missing fund_id in entry")
            return AutoSnapshotResult(False, "Missing fund_id")

        logger.info(f"[AutoSnapshot] ensure_snapshot called for {fund_id}")

        if entry.get("cik"):
            logger.info("[AutoSnapshot] Entry has CIK, using SEC ingestion")
            return self._ingest_from_sec(entry, as_of_override)

        source = (entry.get("auto_source") or "").lower()
        if source == "yfinance":
            logger.info("[AutoSnapshot] Using yfinance source")
            return self._build_from_yfinance(entry, as_of_override)

        logger.warning(
            f"[AutoSnapshot] No automatic snapshot source configured for {fund_id}"
        )
        return AutoSnapshotResult(False, "No automatic snapshot source configured")

    # ------------------------------------------------------------------ #
    def _ingest_from_sec(
        self,
        entry: Dict[str, object],
        as_of_override: Optional[str],
    ) -> AutoSnapshotResult:
        """Run the N-PORT ingestion pipeline for the fund."""
        import logging

        logger = logging.getLogger(__name__)

        fund_id = entry.get("fund_id", "unknown")
        logger.info(f"[AutoSnapshot] Starting SEC ingestion for {fund_id}")

        try:
            from pipeline.ingest_nport import NPORTIngestionPipeline
        except ImportError as exc:  # pragma: no cover - defensive
            logger.error(f"[AutoSnapshot] Import error: {exc}")
            return AutoSnapshotResult(
                False, f"Unable to import ingestion pipeline: {exc}"
            )

        if self._pipeline is None:
            logger.info("[AutoSnapshot] Initializing NPORT pipeline...")
            self._pipeline = NPORTIngestionPipeline(
                base_path=self._base_path,
                registry_path=self._base_path / "fund_registry.yaml",
            )
            logger.info("[AutoSnapshot] NPORT pipeline initialized")

        target_date: Optional[date] = None
        if as_of_override:
            try:
                target_date = datetime.strptime(as_of_override, "%Y-%m-%d").date()
                logger.info(f"[AutoSnapshot] Target date: {target_date}")
            except ValueError:
                target_date = None

        logger.info(f"[AutoSnapshot] Calling ingest_fund for {fund_id} (force=True)...")
        import time

        start_time = time.time()

        try:
            success = self._pipeline.ingest_fund(
                fund_id=entry["fund_id"],
                target_date=target_date,
                force=True,
            )
            elapsed = time.time() - start_time
            logger.info(
                f"[AutoSnapshot] ingest_fund completed in {elapsed:.2f}s, success={success}"
            )
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[AutoSnapshot] ingest_fund failed after {elapsed:.2f}s: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return AutoSnapshotResult(False, f"Ingestion error: {e}")

        message = "Ingestion run completed" if success else "Ingestion failed"
        return AutoSnapshotResult(success, message)

    # ------------------------------------------------------------------ #
    def _build_from_yfinance(
        self,
        entry: Dict[str, object],
        as_of_override: Optional[str],
    ) -> AutoSnapshotResult:
        if yf is None:
            return AutoSnapshotResult(False, "yfinance is not installed")

        tickers = list(self._iterate_tickers(entry))
        if not tickers:
            return AutoSnapshotResult(False, "No ticker defined for yfinance snapshot")

        ticker = tickers[0]
        try:
            yf_ticker = yf.Ticker(ticker)
        except Exception as exc:
            return AutoSnapshotResult(False, f"Failed to create yfinance ticker: {exc}")

        holdings_df: Optional[pd.DataFrame] = None
        funds_data = getattr(yf_ticker, "funds_data", None)
        if funds_data is not None:
            try:
                top_holdings = funds_data.top_holdings
            except Exception:
                top_holdings = pd.DataFrame()

            if top_holdings is not None and not top_holdings.empty:
                holdings_df = top_holdings.reset_index()

        if holdings_df is None or holdings_df.empty:
            fallback = entry.get("fallback_holdings") or []
            holdings_df = self._build_from_fallback(fallback)
            if holdings_df is None:
                return AutoSnapshotResult(
                    False, "No holdings data available from yfinance or fallback"
                )
        else:
            holdings_df = self._normalise_yfinance_df(holdings_df)
            holdings_df = self._enrich_with_security_metadata(holdings_df)

        as_of = (
            as_of_override
            or entry.get("default_as_of")
            or datetime.today().strftime("%Y-%m-%d")
        )

        success = self._write_snapshot(entry["fund_id"], as_of, holdings_df, entry)
        message = "yfinance snapshot created" if success else "Failed to write snapshot"
        return AutoSnapshotResult(success, message)

    @staticmethod
    def _iterate_tickers(entry: Dict[str, object]) -> Iterable[str]:
        tickers = entry.get("tickers", [])
        if isinstance(tickers, str):
            yield tickers
        elif isinstance(tickers, Iterable):
            for ticker in tickers:
                if isinstance(ticker, str):
                    yield ticker

    @staticmethod
    def _normalise_yfinance_df(raw_df: pd.DataFrame) -> pd.DataFrame:
        working = raw_df.rename(
            columns={
                "Symbol": "instrument_ticker",
                "Name": "instrument_name_raw",
                "Holding Percent": "Weight",
            }
        ).copy()

        if "Weight" not in working.columns:
            working["Weight"] = None

        working["Weight"] = pd.to_numeric(working["Weight"], errors="coerce")
        if (
            working["Weight"].max(skipna=True) is not None
            and working["Weight"].max(skipna=True) > 1
        ):
            working["Weight"] = working["Weight"] / 100.0

        total = working["Weight"].sum(skipna=True)
        if not total or pd.isna(total):
            if len(working.index) > 0:
                working["Weight"] = 1.0 / len(working.index)
            else:
                working["Weight"] = None
        else:
            working["Weight"] = working["Weight"] / total

        working["instrument_ticker"] = working["instrument_ticker"].fillna(
            working["instrument_name_raw"]
        )
        working["Symbol"] = working["instrument_ticker"]
        working["instrument_isin"] = None
        working["Country"] = "Unknown"
        working["Sector"] = "Unknown"
        working["Asset_Class"] = "Equity"

        cols = [
            "instrument_ticker",
            "instrument_name_raw",
            "instrument_isin",
            "Weight",
            "Symbol",
            "Country",
            "Sector",
            "Asset_Class",
        ]
        return working[cols]

    @staticmethod
    def _build_from_fallback(fallback_data) -> Optional[pd.DataFrame]:
        if not fallback_data:
            return None

        rows = []
        for item in fallback_data:
            symbol = item.get("symbol")
            weight = item.get("weight")
            if symbol is None or weight is None:
                continue
            rows.append(
                {
                    "instrument_ticker": symbol,
                    "instrument_name_raw": item.get("name", symbol),
                    "instrument_isin": item.get("isin"),
                    "Weight": float(weight),
                    "Symbol": symbol,
                    "Country": item.get("country", "Unknown"),
                    "Sector": item.get("sector", "Unknown"),
                    "Asset_Class": item.get("asset_class", "Equity"),
                }
            )

        if not rows:
            return None

        df = pd.DataFrame(rows)
        total = df["Weight"].sum()
        if total:
            df["Weight"] = df["Weight"] / total
        return df

    def _enrich_with_security_metadata(
        self, df: pd.DataFrame, limit: int = 40
    ) -> pd.DataFrame:
        if yf is None or df.empty:
            return df

        df = df.copy()
        for idx in df.head(limit).index:
            symbol = df.at[idx, "instrument_ticker"]
            if not isinstance(symbol, str) or not symbol:
                continue
            try:
                info = yf.Ticker(symbol).info  # type: ignore[attr-defined]
            except Exception:
                continue

            country = info.get("country") or info.get("countryIso")
            sector = info.get("sector")
            asset_class = info.get("quoteType")

            if country:
                df.at[idx, "Country"] = country
            if sector:
                df.at[idx, "Sector"] = sector
            if asset_class and asset_class.upper() in {"EQUITY", "ETF"}:
                df.at[idx, "Asset_Class"] = "Equity"

        df["Country"] = df["Country"].fillna("Unknown")
        df["Sector"] = df["Sector"].fillna("Unknown")
        df["Asset_Class"] = df["Asset_Class"].fillna("Equity")
        return df

    def _get_fund_name(self, entry: Dict[str, object]) -> str:
        """Get clean fund name for directory structure."""
        tickers = list(self._iterate_tickers(entry))
        if tickers:
            return tickers[0]
        fund_id = entry.get("fund_id", "unknown")
        return fund_id.replace("=", "_").replace("/", "_")

    def _write_snapshot(
        self,
        fund_id: str,
        as_of: str,
        df: pd.DataFrame,
        entry: Optional[Dict[str, object]] = None,
    ) -> bool:
        try:
            # Get fund name
            if entry:
                fund_name = self._get_fund_name(entry)
            else:
                fund_name = fund_id.replace("=", "_").replace("/", "_")

            # New structure: data/funds/[fund_name]/[date]/holdings.csv
            date_dir = self._funds_dir / fund_name / as_of
            date_dir.mkdir(parents=True, exist_ok=True)

            df = df.copy()
            if "Weight" not in df.columns or df["Weight"].sum(skipna=True) in (None, 0):
                if len(df.index) > 0:
                    df["Weight"] = 1.0 / len(df.index)
            else:
                total_weight = df["Weight"].sum()
                if total_weight:
                    df["Weight"] = df["Weight"] / total_weight

            df["fund_id"] = fund_id
            df["as_of"] = as_of
            df["instrument_isin"] = df.get("instrument_isin")
            df["Symbol"] = df.get("Symbol", df.get("instrument_ticker"))
            df["Country"] = df.get("Country", "Unknown")
            df["Sector"] = df.get("Sector", "Unknown")
            df["Asset_Class"] = df.get("Asset_Class", "Equity")

            column_order = [
                "fund_id",
                "as_of",
                "instrument_ticker",
                "instrument_name_raw",
                "instrument_isin",
                "Weight",
                "Symbol",
                "Country",
                "Sector",
                "Asset_Class",
            ]
            for column in column_order:
                if column not in df.columns:
                    df[column] = None
            df = df[column_order]

            # Simple structure: just save holdings.csv directly
            df.to_csv(date_dir / "holdings.csv", index=False)
            return True
        except Exception:
            return False
