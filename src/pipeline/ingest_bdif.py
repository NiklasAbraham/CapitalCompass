"""BDIF (AMF) ingestion orchestrator for French UCITS reports."""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.bdif_discovery import BDIFDiscovery, BDIFReportMetadata
from pipeline.bdif_download import BDIFDownloader
from pipeline.bdif_parser import BDIFParser
from pipeline.bdif_enrichment import BDIFEnrichment
from pipeline.bdif_qa import BDIFQualityAssurance


class BDIFIngestionPipeline:
    """Orchestrate the full BDIF ingestion pipeline."""

    def __init__(
        self,
        base_path: Optional[Path] = None,
        registry_path: Optional[Path] = None,
    ):
        if base_path:
            self.base_path = Path(base_path)
        else:
            project_root = Path(__file__).resolve().parent.parent.parent
            self.base_path = project_root / "data"

        self.registry_path = (
            Path(registry_path) if registry_path else self.base_path / "pipeline" / "fund_registry.yaml"
        )

        self.raw_dir = self.base_path / "raw"
        self.silver_dir = self.base_path / "silver"
        self.gold_dir = self.base_path / "gold_holdings"
        self.qa_dir = self.base_path / "qa"

        for directory in [self.raw_dir, self.silver_dir, self.gold_dir, self.qa_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        self.discovery = BDIFDiscovery()
        self.downloader = BDIFDownloader(self.raw_dir)
        self.parser = BDIFParser()
        self.enrichment = BDIFEnrichment()
        self.qa = BDIFQualityAssurance(self.qa_dir)

        self.registry = self._load_registry()

    def _load_registry(self) -> dict:
        if not self.registry_path.exists():
            print(f"Registry not found: {self.registry_path}")
            return {}

        with self.registry_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}

        return data.get("funds", {})

    def ingest_fund(
        self,
        fund_id: str,
        target_date: Optional[date] = None,
        force: bool = False,
    ) -> bool:
        print(f"\n{'='*60}")
        print(f"Ingesting BDIF data for {fund_id}")
        print(f"{'='*60}\n")

        fund_config = self.registry.get(fund_id)
        if not fund_config:
            print(f"Error: Fund {fund_id} not found in registry")
            return False

        isin = fund_config.get("isin") or fund_config.get("share_class_isin")
        if not isin or not isin.startswith("FR"):
            print(f"Error: ISIN not specified or not French for fund {fund_id}")
            return False

        if not force and not target_date:
            latest_as_of = self._get_latest_as_of(fund_id)
            if latest_as_of:
                freshness_days = fund_config.get("freshness_days", 185)
                days_old = (date.today() - latest_as_of).days
                if days_old < freshness_days:
                    print(f"Fresh data exists (as_of={latest_as_of}, {days_old} days old)")
                    print(f"Skipping ingestion (freshness threshold: {freshness_days} days)")
                    return True

        reports = self.discovery.discover_reports(isin=isin, target_date=target_date)
        if not reports:
            print(f"No BDIF reports found for ISIN {isin}")
            return False

        selected_report: Optional[BDIFReportMetadata] = None
        if target_date:
            for report in reports:
                if report.as_of == target_date:
                    selected_report = report
                    break
            if not selected_report:
                print("No matching report for target date")
                return False
        else:
            selected_report = reports[0]

        print("\nSelected report:")
        print(f"  Date: {selected_report.as_of}")
        print(f"  Type: {selected_report.nature_document}")
        print(f"  URL: {selected_report.pdf_url}")

        pdf_path = self.downloader.download_report(
            pdf_url=selected_report.pdf_url,
            isin=isin,
            as_of_date=selected_report.as_of.strftime("%Y-%m-%d"),
            record_id=selected_report.record_id,
        )

        if not pdf_path or not pdf_path.exists():
            print("Download failed")
            return False

        holdings, metadata = self.parser.parse_report(
            pdf_path=pdf_path,
            fund_id=fund_id,
        )

        if not holdings:
            print("No holdings extracted from report")
            return False

        as_of_date = metadata["as_of"]
        silver_df = self.parser.to_dataframe(holdings)
        silver_path = self._save_silver(silver_df, fund_id, as_of_date)
        print(f"Saved silver holdings: {silver_path}")

        gold_df = self.enrichment.enrich_holdings(silver_df)
        gold_path = self._save_gold(gold_df, fund_id, as_of_date)
        print(f"Saved gold holdings: {gold_path}")

        qa_result = self.qa.validate_holdings(gold_df, fund_id, as_of_date)

        print(f"\n{'='*60}")
        print(f"Ingestion complete for {fund_id}")
        print(f"  As of: {as_of_date}")
        print(f"  Holdings: {len(gold_df)}")
        print(f"  QA status: {qa_result.status.upper()}")
        print(f"{'='*60}\n")

        return qa_result.status == "pass"

    def _get_latest_as_of(self, fund_id: str) -> Optional[date]:
        fund_dir = self.gold_dir / f"fund_id={fund_id}"
        if not fund_dir.exists():
            return None

        as_of_dates = []
        for as_of_dir in fund_dir.glob("as_of=*"):
            date_str = as_of_dir.name.split("=")[1]
            try:
                as_of_dates.append(datetime.strptime(date_str, "%Y-%m-%d").date())
            except ValueError:
                continue

        return max(as_of_dates) if as_of_dates else None

    def _save_silver(self, df, fund_id: str, as_of_date: str) -> Path:
        output_dir = self.silver_dir / f"fund_id={fund_id}" / f"as_of={as_of_date}"
        output_dir.mkdir(parents=True, exist_ok=True)
        version = self._next_version(output_dir)
        output_path = output_dir / f"version={version}.csv"
        df.to_csv(output_path, index=False)
        return output_path

    def _save_gold(self, df, fund_id: str, as_of_date: str) -> Path:
        output_dir = self.gold_dir / f"fund_id={fund_id}" / f"as_of={as_of_date}"
        output_dir.mkdir(parents=True, exist_ok=True)
        version = self._next_version(output_dir)
        output_path = output_dir / f"version={version}"
        output_path.mkdir(exist_ok=True)
        csv_path = output_path / "holdings.csv"
        df.to_csv(csv_path, index=False)
        return csv_path

    def _next_version(self, directory: Path) -> int:
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
    force: bool = False,
):
    pipeline = BDIFIngestionPipeline()

    if not fund:
        print("Error: --fund parameter is required")
        print("Usage: python ingest_bdif.py --fund FR0011550185 [--date YYYY-MM-DD] [--force]")
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

    parser = argparse.ArgumentParser(description="Ingest BDIF holdings data")
    parser.add_argument("--fund", type=str, help="Fund ID from registry (e.g., FR0011550185)")
    parser.add_argument("--date", type=str, help="Target date for backfill (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true", help="Force re-ingestion")

    args = parser.parse_args()

    sys.exit(main(
        fund=args.fund,
        date_str=args.date,
        force=args.force,
    ))
