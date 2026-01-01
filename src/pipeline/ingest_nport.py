"""SEC Form N-PORT ingestion orchestrator.

Main entry point for discovering, downloading, parsing, and enriching
N-PORT holdings data from the SEC.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.nport_discovery import FilingMetadata, NPORTDiscovery
from pipeline.nport_download import NPORTDownloader
from pipeline.nport_enrichment import NPORTEnrichment
from pipeline.nport_parser import NPORTParser
from pipeline.nport_qa import NPORTQualityAssurance


class NPORTIngestionPipeline:
    """Orchestrate the full N-PORT ingestion pipeline."""

    def __init__(
        self,
        base_path: Optional[Path] = None,
        registry_path: Optional[Path] = None,
    ):
        """Initialize the pipeline.

        Args:
            base_path: Base data directory
            registry_path: Path to fund registry YAML
        """
        # Determine project root
        if base_path:
            self.base_path = Path(base_path)
        else:
            project_root = Path(__file__).resolve().parent.parent.parent
            self.base_path = project_root / "data" / "pipeline"

        self.registry_path = (
            Path(registry_path)
            if registry_path
            else self.base_path / "fund_registry.yaml"
        )

        # Initialize directory structure - simplified: data/funds/[fund_name]/[date]/
        self.funds_dir = self.base_path.parent / "funds"
        self.funds_dir.mkdir(parents=True, exist_ok=True)

        # Keep reference dir for mappings
        self.reference_dir = self.base_path / "reference"
        self.reference_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.discovery = NPORTDiscovery()
        self.downloader = NPORTDownloader(
            self.funds_dir
        )  # Will store raw files in fund directories
        self.parser = NPORTParser()
        self.enrichment = NPORTEnrichment(self.reference_dir)
        self.qa = NPORTQualityAssurance(
            self.funds_dir
        )  # Will store QA in fund directories

        # Load registry
        self.registry = self._load_registry()

    def _load_registry(self) -> dict:
        """Load fund registry from YAML."""
        if not self.registry_path.exists():
            print(f"Registry not found: {self.registry_path}")
            return {}

        with self.registry_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return data.get("funds", {})

    def ingest_fund(
        self,
        fund_id: str,
        target_date: Optional[date] = None,
        force: bool = False,
    ) -> bool:
        """Ingest holdings for a single fund.

        Args:
            fund_id: Fund identifier from registry
            target_date: Specific date to fetch (for backfills)
            force: Force re-ingestion even if fresh data exists

        Returns:
            True if successful
        """
        print(f"\n{'=' * 60}")
        print(f"Ingesting N-PORT data for {fund_id}")
        print(f"{'=' * 60}\n")

        # Look up fund in registry
        fund_config = self.registry.get(fund_id)
        if not fund_config:
            print(f"Error: Fund {fund_id} not found in registry")
            return False

        cik = fund_config.get("cik")
        if not cik:
            print(f"Error: CIK not specified for fund {fund_id}")
            return False

        # Check if we need to fetch new data
        if not force and not target_date:
            latest_as_of = self._get_latest_as_of(fund_id)
            if latest_as_of:
                freshness_days = fund_config.get("freshness_days", 30)
                days_old = (date.today() - latest_as_of).days

                if days_old < freshness_days:
                    print(
                        f"Fresh data exists (as_of={latest_as_of}, {days_old} days old)"
                    )
                    print(
                        f"Skipping ingestion (freshness threshold: {freshness_days} days)"
                    )
                    return True

        # Discover filings
        if target_date:
            from_date = target_date - timedelta(days=365)
            to_date = target_date + timedelta(days=365)
        else:
            from_date = date.today() - timedelta(days=120)
            to_date = date.today()

        filings = self.discovery.discover_filings(
            cik=cik,
            from_date=from_date,
            to_date=to_date,
            series_id=fund_config.get("series_id"),
            class_id=fund_config.get("class_id"),
        )

        if not filings:
            print(f"No N-PORT filings found for CIK {cik}")
            return False

        def _filing_sort_key(filing: FilingMetadata):
            if target_date:
                return (
                    abs((filing.as_of_date.date() - target_date).days),
                    -int(filing.filing_date.timestamp()),
                )
            return (-int(filing.filing_date.timestamp()),)

        sorted_filings = sorted(filings, key=_filing_sort_key)
        expected_series = fund_config.get("series_id")
        expected_class = fund_config.get("class_id")

        selected_filing: Optional[FilingMetadata] = None
        parsed_metadata = None
        holdings = None
        xml_path: Optional[Path] = None

        for candidate in sorted_filings:
            print("\nProcessing filing:")
            print(f"  Accession: {candidate.accession}")
            print(f"  Filing date: {candidate.filing_date.strftime('%Y-%m-%d')}")
            print(f"  URL: {candidate.primary_doc_url}")

            # Download
            fund_name = self._get_fund_name(fund_id)
            xml_path = self.downloader.download_filing(
                url=candidate.primary_doc_url,
                cik=candidate.cik,
                accession=candidate.accession,
                as_of_date=candidate.as_of_date.strftime("%Y-%m-%d"),
                fund_name=fund_name,
            )

            if not xml_path or not xml_path.exists():
                print("Download failed; trying next filing (if available)")
                continue

            holdings, metadata = self.parser.parse_filing(
                xml_path=xml_path,
                fund_id=fund_id,
                source_url=candidate.primary_doc_url,
            )

            filing_series = metadata.get("series_id")
            filing_classes = metadata.get("class_ids") or []

            if expected_series and filing_series and filing_series != expected_series:
                print(
                    f"Skipping filing {candidate.accession} "
                    f"(series_id={filing_series}) – expected {expected_series}"
                )
                xml_path.unlink(missing_ok=True)
                continue

            if (
                expected_class
                and filing_classes
                and expected_class not in filing_classes
            ):
                print(
                    f"Skipping filing {candidate.accession} "
                    f"(class_ids={', '.join(filing_classes)}) – expected {expected_class}"
                )
                xml_path.unlink(missing_ok=True)
                continue

            if not holdings:
                print(
                    f"No holdings extracted from filing {candidate.accession}; trying next"
                )
                xml_path.unlink(missing_ok=True)
                continue

            selected_filing = candidate
            parsed_metadata = metadata
            break

        if not selected_filing or not parsed_metadata or holdings is None:
            print(
                "Unable to find a filing matching the requested series/class criteria."
            )
            return False

        filing = selected_filing
        metadata = parsed_metadata
        as_of_date = metadata["as_of"]

        # Parse and enrich directly to gold (skip silver step)
        silver_df = self.parser.to_dataframe(holdings)
        gold_df = self.enrichment.enrich_holdings(silver_df)
        gold_path = self._save_gold(gold_df, fund_id, as_of_date)
        print(f"Saved holdings: {gold_path}")

        # Run QA
        qa_result = self.qa.validate_holdings(gold_df, fund_id, as_of_date)

        # Summary
        print(f"\n{'=' * 60}")
        print(f"Ingestion complete for {fund_id}")
        print(f"  As of: {as_of_date}")
        print(f"  Holdings: {len(gold_df)}")
        print(f"  QA status: {qa_result.status.upper()}")
        print(f"{'=' * 60}\n")

        return qa_result.status == "pass"

    def _get_fund_name(self, fund_id: str) -> str:
        """Get a clean fund name for directory structure.

        Args:
            fund_id: Fund identifier

        Returns:
            Clean fund name (ticker or simplified fund_id)
        """
        fund_config = self.registry.get(fund_id, {})
        # Prefer ticker if available
        tickers = fund_config.get("tickers", [])
        if tickers:
            return tickers[0] if isinstance(tickers, list) else tickers
        # Use fund_id, but clean it up
        return fund_id.replace("=", "_").replace("/", "_")

    def _get_latest_as_of(self, fund_id: str) -> Optional[date]:
        """Get the latest as_of date for a fund.

        Args:
            fund_id: Fund identifier

        Returns:
            Latest as_of date or None
        """
        fund_name = self._get_fund_name(fund_id)
        fund_dir = self.funds_dir / fund_name
        if not fund_dir.exists():
            return None

        as_of_dates = []
        for date_dir in fund_dir.iterdir():
            if not date_dir.is_dir():
                continue
            try:
                as_of_dates.append(datetime.strptime(date_dir.name, "%Y-%m-%d").date())
            except ValueError:
                continue

        return max(as_of_dates) if as_of_dates else None

    def _save_gold(self, df, fund_id: str, as_of_date: str) -> Path:
        """Save gold holdings to simplified structure.

        Args:
            df: Holdings DataFrame
            fund_id: Fund identifier
            as_of_date: Report date

        Returns:
            Path to saved file
        """
        fund_name = self._get_fund_name(fund_id)
        output_dir = self.funds_dir / fund_name / as_of_date
        output_dir.mkdir(parents=True, exist_ok=True)

        csv_path = output_dir / "holdings.csv"
        df.to_csv(csv_path, index=False)
        return csv_path

    def _next_version(self, directory: Path) -> int:
        """Determine the next version number.

        Args:
            directory: Directory to check for versions

        Returns:
            Next version number
        """
        existing_versions = []
        for item in directory.glob("version=*"):
            try:
                version = int(item.name.split("=")[1])
                existing_versions.append(version)
            except (ValueError, IndexError):
                continue

        return max(existing_versions, default=0) + 1


def main(
    fund: Optional[str] = None,
    date_str: Optional[str] = None,
    since_str: Optional[str] = None,
    force: bool = False,
):
    """Main entry point.

    Args:
        fund: Fund ID to ingest
        date_str: Specific date to fetch (YYYY-MM-DD)
        since_str: Fetch from this date (YYYY-MM-DD)
        force: Force re-ingestion
    """
    pipeline = NPORTIngestionPipeline()

    if not fund:
        print("Error: --fund parameter is required")
        print("Usage: python ingest_nport.py --fund SPY [--date YYYY-MM-DD] [--force]")
        return 1

    target_date = None
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            print(f"Error: Invalid date format '{date_str}' (expected YYYY-MM-DD)")
            return 1

    success = pipeline.ingest_fund(fund, target_date=target_date, force=force)
    return 0 if success else 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest SEC Form N-PORT holdings data")
    parser.add_argument("--fund", type=str, help="Fund ID from registry (e.g., SPY)")
    parser.add_argument(
        "--date", type=str, help="Target date for backfill (YYYY-MM-DD)"
    )
    parser.add_argument("--since", type=str, help="Fetch from this date (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true", help="Force re-ingestion")

    args = parser.parse_args()

    sys.exit(
        main(
            fund=args.fund,
            date_str=args.date,
            since_str=args.since,
            force=args.force,
        )
    )
