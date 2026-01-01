"""Primary holdings data access built around the point-in-time pipeline design."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

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
        self._gold_root = self._base_path / "gold_holdings"
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

        ticker_upper = ticker.upper()
        cache_key = f"{ticker_upper}:{as_of or 'latest'}:{max_positions or 'all'}"
        if cache_key in self._cache:
            cached_df, cached_meta = self._cache[cache_key]
            return cached_df.copy(), dict(cached_meta)

        entry = self._resolve_fund_entry(ticker_upper)
        if entry is None:
            # Try to resolve by ISIN if ticker looks like an ISIN
            if len(ticker_upper) == 12 and ticker_upper[:2].isalpha():
                entry = self._resolve_fund_entry_by_isin(ticker_upper)
            
            if entry is None:
                raise PrimaryHoldingsError(
                    f"Ticker/ISIN '{ticker}' is not registered in fund registry"
                )

        snapshot = self._discover_snapshot(entry, as_of)
        if snapshot is None:
            raise PrimaryHoldingsError(
                f"No holdings snapshot found for fund '{entry['fund_id']}'"
                + (f" with as_of {as_of}" if as_of else "")
            )

        raw_df = self._load_snapshot(snapshot.path)
        prepared_df = self._prepare_holdings(raw_df, max_positions=max_positions)

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
                if entry.get('share_class_isin') == isin or entry.get('isin') == isin:
                    return entry
                # Also check if fund_id is the ISIN
                if fund_id == isin:
                    return entry
        return None

    def _discover_snapshot(
        self,
        entry: Dict[str, object],
        as_of_override: Optional[str],
    ) -> Optional[SnapshotHandle]:
        fund_id = entry.get("fund_id")
        relative_path = entry.get("gold_path") or f"fund_id={fund_id}"
        fund_root = self._gold_root / relative_path
        if not fund_root.exists():
            auto_result = self._auto_snapshot.ensure_snapshot(entry, as_of_override)
            if auto_result.success:
                return self._discover_snapshot(entry, as_of_override)
            else:
                print(
                    f"Auto snapshot attempt failed for {entry.get('fund_id')}: {auto_result.message}"
                )
            return None

        target_date = None
        if as_of_override:
            try:
                target_date = datetime.strptime(as_of_override, "%Y-%m-%d")
            except ValueError as exc:
                raise PrimaryHoldingsError(
                    f"Invalid as_of override '{as_of_override}' (expected YYYY-MM-DD)"
                ) from exc

        candidates: list[SnapshotHandle] = []
        for as_of_dir in fund_root.glob("as_of=*"):
            date_str = as_of_dir.name.split("=", 1)[1]
            try:
                as_of_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue
            if target_date and as_of_date.date() != target_date.date():
                continue

            for version_dir in as_of_dir.glob("version=*"):
                version_str = version_dir.name.split("=", 1)[1]
                try:
                    version = int(version_str)
                except ValueError:
                    continue

                for file in version_dir.iterdir():
                    if not file.is_file():
                        continue
                    if file.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                        continue
                    candidates.append(
                        SnapshotHandle(
                            fund_id=fund_id,
                            as_of=as_of_date,
                            version=version,
                            path=file,
                        )
                    )

        if not candidates:
            auto_result = self._auto_snapshot.ensure_snapshot(entry, as_of_override)
            if auto_result.success:
                return self._discover_snapshot(entry, as_of_override)
            else:
                print(
                    f"Auto snapshot attempt failed for {entry.get('fund_id')}: {auto_result.message}"
                )
            return None

        candidates.sort(key=lambda snap: (snap.as_of, snap.version))
        return candidates[-1]

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
