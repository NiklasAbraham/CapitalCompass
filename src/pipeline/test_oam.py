"""Test OAM ingestion pipeline with real fund data.

Tests the complete pipeline with LU0908500753 (Amundi Core Stoxx Europe 600 UCITS ETF).
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import date

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.ingest_oam import OAMIngestionPipeline
from pipeline.oam_discovery import OAMDiscovery
from pipeline.oam_download import OAMDownloader
from pipeline.oam_parser import OAMParser


def test_discovery_lu():
    """Test Luxembourg OAM discovery."""
    print("\n" + "="*60)
    print("Testing Luxembourg OAM Discovery")
    print("="*60 + "\n")
    
    discovery = OAMDiscovery()
    isin = "LU0908500753"
    
    reports = discovery.discover_reports(isin=isin, jurisdiction="LU")
    
    print(f"\nFound {len(reports)} report(s) for ISIN {isin}")
    for i, report in enumerate(reports, 1):
        print(f"\nReport {i}:")
        print(f"  Date: {report.as_of}")
        print(f"  Title: {report.title}")
        print(f"  Type: {report.report_type}")
        print(f"  URL: {report.pdf_url}")
    
    assert len(reports) > 0, "Should find at least one report"
    assert reports[0].jurisdiction == "LU", "Should be Luxembourg jurisdiction"
    
    print("\n✓ Discovery test passed")
    return reports


def test_download_lu(reports):
    """Test downloading a Luxembourg report."""
    print("\n" + "="*60)
    print("Testing Luxembourg OAM Download")
    print("="*60 + "\n")
    
    if not reports:
        print("No reports to download")
        return None
    
    # Use the most recent report
    report = reports[0]
    
    project_root = Path(__file__).resolve().parent.parent.parent
    raw_dir = project_root / "data" / "raw"
    
    downloader = OAMDownloader(raw_dir)
    
    pdf_path = downloader.download_report(
        pdf_url=report.pdf_url,
        isin="LU0908500753",
        as_of_date=report.as_of.strftime("%Y-%m-%d"),
        jurisdiction="LU",
    )
    
    assert pdf_path is not None, "Download should succeed"
    assert pdf_path.exists(), "Downloaded file should exist"
    
    print(f"\n✓ Download test passed: {pdf_path}")
    return pdf_path


def test_parser_lu(pdf_path):
    """Test parsing a Luxembourg PDF."""
    print("\n" + "="*60)
    print("Testing OAM PDF Parser")
    print("="*60 + "\n")
    
    if not pdf_path or not pdf_path.exists():
        print("No PDF to parse")
        return None, None
    
    parser = OAMParser()
    
    holdings, metadata = parser.parse_report(
        pdf_path=pdf_path,
        fund_id="LU0908500753",
        source_url="test",
    )
    
    print(f"\nParsed {len(holdings)} holdings")
    print(f"Metadata: {metadata}")
    
    if holdings:
        print("\nFirst 5 holdings:")
        for i, holding in enumerate(holdings[:5], 1):
            print(f"\n  {i}. {holding.instrument_name_raw}")
            print(f"     ISIN: {holding.isin}")
            print(f"     Value: {holding.market_value_local}")
            print(f"     Currency: {holding.currency}")
    
    assert len(holdings) > 0, "Should extract at least some holdings"
    
    print("\n✓ Parser test passed")
    return holdings, metadata


def test_full_pipeline():
    """Test the complete ingestion pipeline."""
    print("\n" + "="*60)
    print("Testing Full OAM Ingestion Pipeline")
    print("="*60 + "\n")
    
    pipeline = OAMIngestionPipeline()
    
    success = pipeline.ingest_fund(
        fund_id="LU0908500753",
        force=True,  # Force re-ingestion for testing
    )
    
    assert success, "Pipeline should complete successfully"
    
    # Verify output files exist
    project_root = Path(__file__).resolve().parent.parent.parent
    gold_dir = project_root / "data" / "pipeline" / "gold_holdings"
    fund_dir = gold_dir / "fund_id=LU0908500753"
    
    assert fund_dir.exists(), "Gold holdings directory should exist"
    
    # Find the most recent as_of directory
    as_of_dirs = list(fund_dir.glob("as_of=*"))
    assert len(as_of_dirs) > 0, "Should have at least one as_of directory"
    
    latest_as_of = max(as_of_dirs, key=lambda p: p.name)
    holdings_file = None
    
    # Find holdings.csv in version directories
    for version_dir in latest_as_of.glob("version=*"):
        csv_file = version_dir / "holdings.csv"
        if csv_file.exists():
            holdings_file = csv_file
            break
    
    assert holdings_file is not None, "Holdings CSV should exist"
    assert holdings_file.exists(), "Holdings CSV file should exist"
    
    # Read and verify the CSV
    import pandas as pd
    df = pd.read_csv(holdings_file)
    
    assert len(df) > 0, "Should have holdings in CSV"
    assert "weight_pct" in df.columns, "Should have weight_pct column"
    assert "isin" in df.columns, "Should have isin column"
    
    print(f"\n✓ Full pipeline test passed")
    print(f"  Holdings file: {holdings_file}")
    print(f"  Number of holdings: {len(df)}")
    print(f"  Total weight: {df['weight_pct'].sum():.2f}%")
    
    return True


def test_backfill():
    """Test backfilling historical data."""
    print("\n" + "="*60)
    print("Testing Backfill Functionality")
    print("="*60 + "\n")
    
    pipeline = OAMIngestionPipeline()
    
    # Try to get a report from 2023
    target_date = date(2023, 12, 31)
    
    success = pipeline.ingest_fund(
        fund_id="LU0908500753",
        target_date=target_date,
        force=True,
    )
    
    if success:
        print("\n✓ Backfill test passed")
    else:
        print("\n⚠ Backfill test: No data found for target date (this is OK)")
    
    return success


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("OAM Pipeline Test Suite")
    print("Testing with ISIN: LU0908500753 (Amundi Core Stoxx Europe 600 UCITS ETF)")
    print("="*80)
    
    try:
        # Test 1: Discovery
        reports = test_discovery_lu()
        
        # Test 2: Download
        pdf_path = test_download_lu(reports)
        
        # Test 3: Parser
        holdings, metadata = test_parser_lu(pdf_path)
        
        # Test 4: Full pipeline
        test_full_pipeline()
        
        # Test 5: Backfill (optional)
        # test_backfill()
        
        print("\n" + "="*80)
        print("ALL TESTS PASSED ✓")
        print("="*80 + "\n")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
