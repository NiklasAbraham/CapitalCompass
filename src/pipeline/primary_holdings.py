"""Primary holdings data access built around the point-in-time pipeline design."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency handled via requirements
    raise ImportError("PyYAML is required for the primary holdings client.") from exc


class PrimaryHoldingsError(RuntimeError):
    """Raised when primary holdings data cannot be retrieved."""


@dataclass
class SnapshotHandle:
    """Represents a single gold snapshot on disk."""

    fund_id: str
    as_of: datetime
    version: int
    path: Path


class PrimaryHoldingsClient:
    """Load holdings from the local primary (issuer / SEC) pipeline artifacts."""

    SUPPORTED_EXTENSIONS = (".csv", ".parquet", ".json")

    def __init__(
        self,
        base_path: Optional[Path | str] = None,
        registry_path: Optional[Path | str] = None,
    ) -> None:
        project_root = Path(__file__).resolve().parent.parent.parent
        self._base_path = (
            Path(base_path) if base_path else project_root / "data" / "pipeline"
        )
        self._registry_path = (
            Path(registry_path)
            if registry_path
            else self._base_path / "fund_registry.yaml"
        )
        # New simplified structure: data/funds/[fund_name]/[date]/
        self._funds_dir = project_root / "data" / "funds"
        self._registry: Dict[str, Dict[str, object]] = {}
        self._ticker_index: Dict[str, str] = {}
        self._load_registry()
        self._cache: Dict[str, Tuple[pd.DataFrame, Dict[str, object]]] = {}
        from pipeline.auto_snapshot import AutoSnapshotManager  # local import

        self._auto_snapshot = AutoSnapshotManager(self._base_path, self._registry)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fetch_holdings(
        self,
        ticker: str,
        as_of: Optional[str] = None,
        max_positions: Optional[int] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, object]]:
        """Return a holdings DataFrame normalised for downstream analysis.

        Args:
            ticker: Ticker symbol or ISIN
            as_of: Optional report date
            max_positions: Optional maximum positions to return
        """
        fetch_start = time.time()
        logger.info(
            f"[PrimaryHoldings] fetch_holdings({ticker}, as_of={as_of}, max_positions={max_positions})"
        )

        ticker_upper = ticker.upper()
        cache_key = f"{ticker_upper}:{as_of or 'latest'}:{max_positions or 'all'}"
        if cache_key in self._cache:
            logger.info(f"[PrimaryHoldings] Using cached data for {ticker}")
            cached_df, cached_meta = self._cache[cache_key]
            return cached_df.copy(), dict(cached_meta)

        logger.info(f"[PrimaryHoldings] Resolving fund entry for {ticker}...")
        resolve_start = time.time()
        entry = self._resolve_fund_entry(ticker_upper)
        if entry is None:
            # Try to resolve by ISIN if ticker looks like an ISIN
            if len(ticker_upper) == 12 and ticker_upper[:2].isalpha():
                logger.info(f"[PrimaryHoldings] Trying ISIN resolution for {ticker}...")
                entry = self._resolve_fund_entry_by_isin(ticker_upper)

            if entry is None:
                logger.error(f"[PrimaryHoldings] Fund entry not found for {ticker}")
                raise PrimaryHoldingsError(
                    f"Ticker/ISIN '{ticker}' is not registered in fund registry"
                )
        logger.info(
            f"[PrimaryHoldings] Resolved to fund_id={entry.get('fund_id')} in {time.time() - resolve_start:.2f}s"
        )

        logger.info(
            f"[PrimaryHoldings] Discovering snapshot for {entry.get('fund_id')}..."
        )
        discover_start = time.time()
        snapshot = self._discover_snapshot(entry, as_of)
        logger.info(
            f"[PrimaryHoldings] Snapshot discovery took {time.time() - discover_start:.2f}s"
        )
        if snapshot is None:
            logger.error(
                f"[PrimaryHoldings] No snapshot found for {entry.get('fund_id')}"
            )
            raise PrimaryHoldingsError(
                f"No holdings snapshot found for fund '{entry['fund_id']}'"
                + (f" with as_of {as_of}" if as_of else "")
            )

        logger.info(f"[PrimaryHoldings] Loading snapshot from {snapshot.path}...")
        load_start = time.time()
        raw_df = self._load_snapshot(snapshot.path)
        logger.info(
            f"[PrimaryHoldings] Loaded {len(raw_df)} rows in {time.time() - load_start:.2f}s"
        )

        logger.info("[PrimaryHoldings] Preparing holdings...")
        prepare_start = time.time()
        prepared_df = self._prepare_holdings(raw_df, max_positions=max_positions)
        logger.info(
            f"[PrimaryHoldings] Prepared {len(prepared_df)} holdings in {time.time() - prepare_start:.2f}s"
        )

        metadata = {
            "fund_id": entry.get("fund_id"),
            "ticker": ticker_upper,
            "as_of": snapshot.as_of.strftime("%Y-%m-%d"),
            "version": snapshot.version,
            "issuer": entry.get("issuer"),
            "source": entry.get("source", "PRIMARY"),
            "snapshot_path": str(snapshot.path),
        }

        self._cache[cache_key] = (prepared_df.copy(), dict(metadata))
        total_time = time.time() - fetch_start
        logger.info(f"[PrimaryHoldings] Total fetch_holdings took {total_time:.2f}s")
        return prepared_df, metadata

    def get_country_exposure(self, holdings: pd.DataFrame) -> Optional[pd.DataFrame]:
        return self._aggregate_dimension(holdings, "Country")

    def get_sector_exposure(self, holdings: pd.DataFrame) -> Optional[pd.DataFrame]:
        return self._aggregate_dimension(holdings, "Sector")

    def get_asset_class_exposure(
        self, holdings: pd.DataFrame
    ) -> Optional[pd.DataFrame]:
        return self._aggregate_dimension(holdings, "Asset_Class")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_registry(self) -> None:
        if not self._registry_path.exists():
            self._registry = {}
            self._ticker_index = {}
            return

        with self._registry_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}

        funds = data.get("funds", {})
        if not isinstance(funds, dict):
            raise PrimaryHoldingsError(
                "fund_registry.yaml must contain a mapping at 'funds'"
            )

        for fund_id, entry in funds.items():
            if not isinstance(entry, dict):
                continue
            entry.setdefault("fund_id", fund_id)
            self._registry[fund_id] = entry
            for ticker in self._iterate_tickers(entry):
                self._ticker_index[ticker.upper()] = fund_id

    @staticmethod
    def _iterate_tickers(entry: Dict[str, object]) -> Iterable[str]:
        tickers = entry.get("tickers", [])
        if isinstance(tickers, str):
            yield tickers
        elif isinstance(tickers, Iterable):
            for ticker in tickers:
                if isinstance(ticker, str):
                    yield ticker

    def _resolve_fund_entry(self, ticker_upper: str) -> Optional[Dict[str, object]]:
        fund_id = self._ticker_index.get(ticker_upper)
        if fund_id:
            return self._registry.get(fund_id)

        # Last resort: brute-force search
        for fund_id, entry in self._registry.items():
            if any(t.upper() == ticker_upper for t in self._iterate_tickers(entry)):
                self._ticker_index[ticker_upper] = fund_id
                return entry
        return None

    def _resolve_fund_entry_by_isin(self, isin: str) -> Optional[Dict[str, object]]:
        """Resolve fund entry by ISIN.

        Args:
            isin: ISIN identifier

        Returns:
            Fund entry or None
        """
        for fund_id, entry in self._registry.items():
            if isinstance(entry, dict):
                if entry.get("share_class_isin") == isin or entry.get("isin") == isin:
                    return entry
                # Also check if fund_id is the ISIN
                if fund_id == isin:
                    return entry
        return None

    def _get_fund_name(self, entry: Dict[str, object]) -> str:
        """Get clean fund name for directory structure.

        Args:
            entry: Fund registry entry

        Returns:
            Clean fund name (ticker or fund_id)
        """
        # Prefer ticker if available
        tickers = entry.get("tickers", [])
        if tickers:
            ticker = tickers[0] if isinstance(tickers, list) else tickers
            if ticker:
                return ticker
        # Fallback to fund_id, cleaned up
        fund_id = entry.get("fund_id", "unknown")
        return fund_id.replace("=", "_").replace("/", "_")

    def _discover_snapshot(
        self,
        entry: Dict[str, object],
        as_of_override: Optional[str],
    ) -> Optional[SnapshotHandle]:
        discover_start = time.time()
        fund_id = entry.get("fund_id")
        fund_name = self._get_fund_name(entry)
        fund_root = self._funds_dir / fund_name
        logger.info(f"[PrimaryHoldings] Looking for snapshot in {fund_root}")

        if not fund_root.exists():
            logger.warning(f"[PrimaryHoldings] Fund root does not exist: {fund_root}")
            logger.info(f"[PrimaryHoldings] Attempting auto snapshot for {fund_id}...")
            auto_start = time.time()
            try:
                auto_result = self._auto_snapshot.ensure_snapshot(entry, as_of_override)
                elapsed = time.time() - auto_start
                logger.info(
                    f"[PrimaryHoldings] Auto snapshot took {elapsed:.2f}s, success={auto_result.success}"
                )
                if auto_result.success:
                    logger.info(
                        "[PrimaryHoldings] Retrying snapshot discovery after auto snapshot..."
                    )
                    return self._discover_snapshot(entry, as_of_override)
                else:
                    logger.warning(
                        f"[PrimaryHoldings] Auto snapshot failed: {auto_result.message}"
                    )
            except Exception as e:
                elapsed = time.time() - auto_start
                logger.error(
                    f"[PrimaryHoldings] Auto snapshot exception after {elapsed:.2f}s: {e}"
                )
                import traceback

                logger.error(traceback.format_exc())
            return None

        target_date = None
        if as_of_override:
            try:
                target_date = datetime.strptime(as_of_override, "%Y-%m-%d")
            except ValueError as exc:
                raise PrimaryHoldingsError(
                    f"Invalid as_of override '{as_of_override}' (expected YYYY-MM-DD)"
                ) from exc

        logger.info("[PrimaryHoldings] Scanning for snapshot files...")
        scan_start = time.time()
        candidates: list[SnapshotHandle] = []

        # New structure: data/funds/[fund_name]/[date]/holdings.csv
        date_dirs = [d for d in fund_root.iterdir() if d.is_dir()]
        logger.info(f"[PrimaryHoldings] Found {len(date_dirs)} date directories")

        for date_dir in date_dirs:
            try:
                as_of_date = datetime.strptime(date_dir.name, "%Y-%m-%d")
            except ValueError:
                continue
            if target_date and as_of_date.date() != target_date.date():
                continue

            # Look for holdings.csv in the date directory
            holdings_file = date_dir / "holdings.csv"
            if holdings_file.exists() and holdings_file.is_file():
                candidates.append(
                    SnapshotHandle(
                        fund_id=fund_id,
                        as_of=as_of_date,
                        version=1,  # No versioning in new structure
                        path=holdings_file,
                    )
                )
                logger.info(f"[PrimaryHoldings] Found holdings in {date_dir.name}")

        logger.info(
            f"[PrimaryHoldings] Found {len(candidates)} candidate snapshots in {time.time() - scan_start:.2f}s"
        )

        if not candidates:
            logger.warning(
                f"[PrimaryHoldings] No candidates found, trying auto snapshot for {fund_id}..."
            )
            auto_start = time.time()
            try:
                auto_result = self._auto_snapshot.ensure_snapshot(entry, as_of_override)
                elapsed = time.time() - auto_start
                logger.info(
                    f"[PrimaryHoldings] Auto snapshot took {elapsed:.2f}s, success={auto_result.success}"
                )
                if auto_result.success:
                    logger.info(
                        "[PrimaryHoldings] Retrying snapshot discovery after auto snapshot..."
                    )
                    return self._discover_snapshot(entry, as_of_override)
                else:
                    logger.warning(
                        f"[PrimaryHoldings] Auto snapshot failed: {auto_result.message}"
                    )
            except Exception as e:
                elapsed = time.time() - auto_start
                logger.error(
                    f"[PrimaryHoldings] Auto snapshot exception after {elapsed:.2f}s: {e}"
                )
                import traceback

                logger.error(traceback.format_exc())
            return None

        candidates.sort(key=lambda snap: (snap.as_of, snap.version))
        selected = candidates[-1]
        logger.info(
            f"[PrimaryHoldings] Selected snapshot: {selected.path} (as_of={selected.as_of.date()}, version={selected.version})"
        )
        logger.info(
            f"[PrimaryHoldings] Total discovery took {time.time() - discover_start:.2f}s"
        )
        return selected

    def _load_snapshot(self, path: Path) -> pd.DataFrame:
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(path)
        if suffix == ".parquet":
            return pd.read_parquet(path)  # pragma: no cover - optional dependency
        if suffix == ".json":
            return pd.read_json(path)
        raise PrimaryHoldingsError(f"Unsupported snapshot format: {path.suffix}")

    def _prepare_holdings(
        self,
        df: pd.DataFrame,
        max_positions: Optional[int],
    ) -> pd.DataFrame:
        if df.empty:
            raise PrimaryHoldingsError("Holdings snapshot is empty")

        working = df.copy()

        rename_map = {
            "instrument_ticker": "Symbol",
            "instrument_name": "Name",
            "country": "Country",
            "sector": "Sector",
            "asset_class": "Asset_Class",
        }
        for raw_col, canonical_col in rename_map.items():
            if raw_col in working.columns and canonical_col not in working.columns:
                working[canonical_col] = working[raw_col]

        if "Symbol" not in working.columns:
            working["Symbol"] = working.get("instrument_isin")

        if "Name" not in working.columns:
            working["Name"] = working.get("instrument_isin")

        # Determine weights
        weight_cols = [
            "weight_pct_recalc",
            "weight_pct_issuer",
            "weight_pct_raw",
            "Weight",
        ]
        weight_series = None
        for col in weight_cols:
            if col in working.columns:
                weight_series = pd.to_numeric(working[col], errors="coerce")
                if weight_series.notna().any():
                    break

        if weight_series is None or weight_series.isna().all():
            if "market_value_eur" in working.columns:
                mv = pd.to_numeric(working["market_value_eur"], errors="coerce")
            else:
                mv = pd.to_numeric(working.get("market_value_local"), errors="coerce")
            if mv is None or mv.isna().all():
                raise PrimaryHoldingsError(
                    "Snapshot is missing weight and market value information"
                )
            weight_series = mv / mv.sum()

        total_weight = weight_series.sum()
        if total_weight == 0 or pd.isna(total_weight):
            raise PrimaryHoldingsError("Holdings snapshot has zero total weight")

        working["Weight"] = (weight_series / total_weight).astype(float)

        # Trim to the requested number of positions
        working = working.sort_values("Weight", ascending=False)
        if max_positions is not None:
            working = working.head(max_positions)
            working["Weight"] = working["Weight"] / working["Weight"].sum()

        for column in ("Country", "Sector", "Asset_Class"):
            if column in working.columns:
                working[column] = working[column].fillna("Unknown")

        # Keep provenance-rich columns for downstream display
        return working.reset_index(drop=True)

    @staticmethod
    def _aggregate_dimension(
        holdings: pd.DataFrame, column: str
    ) -> Optional[pd.DataFrame]:
        if column not in holdings.columns:
            return None
        subset = holdings[[column, "Weight"]].copy()
        subset = subset[subset[column].notna()]
        if subset.empty:
            return None
        aggregated = (
            subset.groupby(column)["Weight"]
            .sum()
            .reset_index()
            .sort_values("Weight", ascending=False)
        )
        return aggregated.rename(columns={"Weight": "Weight"})
