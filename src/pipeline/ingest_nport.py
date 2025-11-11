"""SEC Form N-PORT ingestion orchestrator.

Main entry point for discovering, downloading, parsing, and enriching
N-PORT holdings data from the SEC.
"""

from __future__ import annotations

import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional
import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.nport_discovery import NPORTDiscovery, FilingMetadata
from pipeline.nport_download import NPORTDownloader
from pipeline.nport_parser import NPORTParser
from pipeline.nport_enrichment import NPORTEnrichment
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
            Path(registry_path) if registry_path
            else self.base_path / "fund_registry.yaml"
        )
        
        # Initialize directory structure
        self.raw_dir = self.base_path.parent / "raw"
        self.silver_dir = self.base_path / "silver_holdings"
        self.gold_dir = self.base_path / "gold_holdings"
        self.qa_dir = self.base_path.parent / "qa"
        self.reference_dir = self.base_path / "reference"
        
        # Create directories
        for directory in [self.raw_dir, self.silver_dir, self.gold_dir, self.qa_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.discovery = NPORTDiscovery()
        self.downloader = NPORTDownloader(self.raw_dir)
        self.parser = NPORTParser()
        self.enrichment = NPORTEnrichment(self.reference_dir)
        self.qa = NPORTQualityAssurance(self.qa_dir)
        
        # Load registry
        self.registry = self._load_registry()
    
    def _load_registry(self) -> dict:
        """Load fund registry from YAML."""
        if not self.registry_path.exists():
            print(f"Registry not found: {self.registry_path}")
            return {}
        
        with self.registry_path.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        return data.get('funds', {})
    
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
        print(f"\n{'='*60}")
        print(f"Ingesting N-PORT data for {fund_id}")
        print(f"{'='*60}\n")
        
        # Look up fund in registry
        fund_config = self.registry.get(fund_id)
        if not fund_config:
            print(f"Error: Fund {fund_id} not found in registry")
            return False
        
        cik = fund_config.get('cik')
        if not cik:
            print(f"Error: CIK not specified for fund {fund_id}")
            return False
        
        # Check if we need to fetch new data
        if not force and not target_date:
            latest_as_of = self._get_latest_as_of(fund_id)
            if latest_as_of:
                freshness_days = fund_config.get('freshness_days', 30)
                days_old = (date.today() - latest_as_of).days
                
                if days_old < freshness_days:
                    print(f"Fresh data exists (as_of={latest_as_of}, {days_old} days old)")
                    print(f"Skipping ingestion (freshness threshold: {freshness_days} days)")
                    return True
        
        # Discover filings
        from_date = target_date if target_date else date.today() - timedelta(days=90)
        to_date = target_date if target_date else date.today()
        
        filings = self.discovery.discover_filings(
            cik=cik,
            from_date=from_date,
            to_date=to_date,
            series_id=fund_config.get('series_id'),
            class_id=fund_config.get('class_id'),
        )
        
        if not filings:
            print(f"No N-PORT filings found for CIK {cik}")
            return False
        
        # Process the most recent filing
        filing = filings[-1]
        print(f"\nProcessing filing:")
        print(f"  Accession: {filing.accession}")
        print(f"  Filing date: {filing.filing_date.strftime('%Y-%m-%d')}")
        print(f"  URL: {filing.primary_doc_url}")
        
        # Download
        xml_path = self.downloader.download_filing(
            url=filing.primary_doc_url,
            cik=filing.cik,
            accession=filing.accession,
            as_of_date=filing.as_of_date.strftime('%Y-%m-%d'),
        )
        
        if not xml_path or not xml_path.exists():
            print("Download failed")
            return False
        
        # Parse to silver
        holdings, metadata = self.parser.parse_filing(
            xml_path=xml_path,
            fund_id=fund_id,
            source_url=filing.primary_doc_url,
        )
        
        if not holdings:
            print("No holdings extracted from filing")
            return False
        
        as_of_date = metadata['as_of']
        
        # Save silver holdings
        silver_df = self.parser.to_dataframe(holdings)
        silver_path = self._save_silver(silver_df, fund_id, as_of_date)
        print(f"Saved silver holdings: {silver_path}")
        
        # Enrich to gold
        gold_df = self.enrichment.enrich_holdings(silver_df)
        gold_path = self._save_gold(gold_df, fund_id, as_of_date)
        print(f"Saved gold holdings: {gold_path}")
        
        # Run QA
        qa_result = self.qa.validate_holdings(gold_df, fund_id, as_of_date)
        
        # Summary
        print(f"\n{'='*60}")
        print(f"Ingestion complete for {fund_id}")
        print(f"  As of: {as_of_date}")
        print(f"  Holdings: {len(gold_df)}")
        print(f"  QA status: {qa_result.status.upper()}")
        print(f"{'='*60}\n")
        
        return qa_result.status == 'pass'
    
    def _get_latest_as_of(self, fund_id: str) -> Optional[date]:
        """Get the latest as_of date for a fund.
        
        Args:
            fund_id: Fund identifier
            
        Returns:
            Latest as_of date or None
        """
        fund_dir = self.gold_dir / f"fund_id={fund_id}"
        if not fund_dir.exists():
            return None
        
        as_of_dates = []
        for as_of_dir in fund_dir.glob("as_of=*"):
            date_str = as_of_dir.name.split('=')[1]
            try:
                as_of_dates.append(datetime.strptime(date_str, "%Y-%m-%d").date())
            except ValueError:
                continue
        
        return max(as_of_dates) if as_of_dates else None
    
    def _save_silver(self, df, fund_id: str, as_of_date: str) -> Path:
        """Save silver holdings.
        
        Args:
            df: Holdings DataFrame
            fund_id: Fund identifier
            as_of_date: Report date
            
        Returns:
            Path to saved file
        """
        output_dir = self.silver_dir / f"fund_id={fund_id}" / f"as_of={as_of_date}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine version
        version = self._next_version(output_dir)
        output_path = output_dir / f"version={version}.csv"
        
        df.to_csv(output_path, index=False)
        return output_path
    
    def _save_gold(self, df, fund_id: str, as_of_date: str) -> Path:
        """Save gold holdings.
        
        Args:
            df: Holdings DataFrame
            fund_id: Fund identifier
            as_of_date: Report date
            
        Returns:
            Path to saved file
        """
        output_dir = self.gold_dir / f"fund_id={fund_id}" / f"as_of={as_of_date}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Determine version
        version = self._next_version(output_dir)
        output_path = output_dir / f"version={version}"
        output_path.mkdir(exist_ok=True)
        
        csv_path = output_path / "holdings.csv"
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
                version = int(item.name.split('=')[1])
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
    parser.add_argument("--date", type=str, help="Target date for backfill (YYYY-MM-DD)")
    parser.add_argument("--since", type=str, help="Fetch from this date (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true", help="Force re-ingestion")
    
    args = parser.parse_args()
    
    sys.exit(main(
        fund=args.fund,
        date_str=args.date,
        since_str=args.since,
        force=args.force,
    ))

