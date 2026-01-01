"""Manual test script for OAM ingestion with direct PDF URLs.

This script allows testing the OAM pipeline with manually specified URLs
or local PDF files, bypassing the discovery mechanism.
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.oam_download import OAMDownloader
from pipeline.oam_parser import OAMParser
from pipeline.oam_enrichment import OAMEnrichment
from pipeline.oam_qa import OAMQualityAssurance


def test_with_url(
    isin: str = "LU0292107645",
    url: str = "",
    report_date: str = "",
):
    """Test ingestion with a manually specified URL.
    
    Args:
        isin: ISIN identifier
        url: Direct URL to PDF report
        report_date: Report date (YYYY-MM-DD)
    """
    # Set up directories
    project_root = Path(__file__).parent.parent.parent
    raw_dir = project_root / "data" / "raw"
    silver_dir = project_root / "data" / "pipeline" / "silver"
    gold_dir = project_root / "data" / "pipeline" / "gold_holdings"
    qa_dir = project_root / "data" / "qa"
    
    for directory in [raw_dir, silver_dir, gold_dir, qa_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    
    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")
    
    domicile = isin[:2]
    oam = "LuxSE" if domicile == "LU" else "Bundesanzeiger"
    
    print(f"\nManual OAM Test")
    print(f"{'='*60}")
    print(f"ISIN: {isin}")
    print(f"OAM: {oam}")
    print(f"URL: {url}")
    print(f"Report date: {report_date}")
    print(f"{'='*60}\n")
    
    # Download
    downloader = OAMDownloader(raw_dir)
    pdf_path = downloader.download_report(url, isin, oam, report_date)
    
    if not pdf_path or not pdf_path.exists():
        print("❌ Download failed")
        return False
    
    print(f"✓ Downloaded to {pdf_path}")
    
    # Parse
    try:
        parser = OAMParser()
        holdings, metadata = parser.parse_filing(pdf_path, isin, url)
    except ImportError as e:
        print(f"❌ PDF parsing failed: {e}")
        print("\nTip: Install pdfplumber: pip install pdfplumber")
        return False
    
    if not holdings:
        print("❌ No holdings extracted")
        print("\nTip: The PDF may not contain a holdings table, or the table format")
        print("may not be recognized. Check the PDF manually.")
        return False
    
    print(f"✓ Parsed {len(holdings)} holdings")
    
    # Save silver
    silver_df = parser.to_dataframe(holdings)
    silver_path = silver_dir / f"isin={isin}" / f"report_date={report_date}"
    silver_path.mkdir(parents=True, exist_ok=True)
    silver_file = silver_path / "version=1.csv"
    silver_df.to_csv(silver_file, index=False)
    print(f"✓ Saved silver: {silver_file}")
    
    # Enrich
    enrichment = OAMEnrichment()
    gold_df = enrichment.enrich_holdings(silver_df)
    
    # Save gold
    gold_path = gold_dir / f"isin={isin}" / f"report_date={report_date}" / "version=1"
    gold_path.mkdir(parents=True, exist_ok=True)
    gold_file = gold_path / "holdings.csv"
    gold_df.to_csv(gold_file, index=False)
    print(f"✓ Saved gold: {gold_file}")
    
    # QA
    qa = OAMQualityAssurance(qa_dir)
    qa_result = qa.validate_holdings(gold_df, isin, report_date)
    
    print(f"\n{'='*60}")
    print(f"Test Complete")
    print(f"{'='*60}")
    print(f"Holdings: {len(gold_df)}")
    print(f"Status: {qa_result.status.upper()}")
    
    if qa_result.status == 'pass':
        print("\n✓ All quality checks passed!")
        return True
    else:
        print("\n✗ Some quality checks failed")
        return False


def test_with_local_file(
    isin: str = "LU0292107645",
    pdf_path: str = "",
    report_date: str = "",
):
    """Test ingestion with a local PDF file.
    
    Args:
        isin: ISIN identifier
        pdf_path: Path to local PDF file
        report_date: Report date (YYYY-MM-DD)
    """
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"❌ PDF file not found: {pdf_path}")
        return False
    
    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")
    
    print(f"\nManual OAM Test (Local File)")
    print(f"{'='*60}")
    print(f"ISIN: {isin}")
    print(f"PDF: {pdf_path}")
    print(f"Report date: {report_date}")
    print(f"{'='*60}\n")
    
    # Parse
    try:
        parser = OAMParser()
        holdings, metadata = parser.parse_filing(pdf_file, isin, str(pdf_file))
    except ImportError as e:
        print(f"❌ PDF parsing failed: {e}")
        print("\nTip: Install pdfplumber: pip install pdfplumber")
        return False
    
    if not holdings:
        print("❌ No holdings extracted")
        return False
    
    print(f"✓ Parsed {len(holdings)} holdings")
    
    # Set up directories
    project_root = Path(__file__).parent.parent.parent
    silver_dir = project_root / "data" / "pipeline" / "silver"
    gold_dir = project_root / "data" / "pipeline" / "gold_holdings"
    qa_dir = project_root / "data" / "qa"
    
    for directory in [silver_dir, gold_dir, qa_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    
    # Save silver
    silver_df = parser.to_dataframe(holdings)
    silver_path = silver_dir / f"isin={isin}" / f"report_date={report_date}"
    silver_path.mkdir(parents=True, exist_ok=True)
    silver_file = silver_path / "version=1.csv"
    silver_df.to_csv(silver_file, index=False)
    print(f"✓ Saved silver: {silver_file}")
    
    # Enrich
    enrichment = OAMEnrichment()
    gold_df = enrichment.enrich_holdings(silver_df)
    
    # Save gold
    gold_path = gold_dir / f"isin={isin}" / f"report_date={report_date}" / "version=1"
    gold_path.mkdir(parents=True, exist_ok=True)
    gold_file = gold_path / "holdings.csv"
    gold_df.to_csv(gold_file, index=False)
    print(f"✓ Saved gold: {gold_file}")
    
    # QA
    qa = OAMQualityAssurance(qa_dir)
    qa_result = qa.validate_holdings(gold_df, isin, report_date)
    
    print(f"\n{'='*60}")
    print(f"Test Complete")
    print(f"{'='*60}")
    print(f"Holdings: {len(gold_df)}")
    print(f"Status: {qa_result.status.upper()}")
    
    if qa_result.status == 'pass':
        print("\n✓ All quality checks passed!")
        return True
    else:
        print("\n✗ Some quality checks failed")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Manual OAM testing")
    parser.add_argument("--isin", type=str, default="LU0292107645", help="ISIN")
    parser.add_argument("--url", type=str, default="", help="Direct URL to PDF file")
    parser.add_argument("--file", type=str, default="", help="Path to local PDF file")
    parser.add_argument("--report-date", type=str, default="", help="Report date (YYYY-MM-DD)")
    
    args = parser.parse_args()
    
    if args.file:
        test_with_local_file(args.isin, args.file, args.report_date)
    elif args.url:
        test_with_url(args.isin, args.url, args.report_date)
    else:
        print("Error: Please provide --url or --file")
        print("\nUsage:")
        print("  python test_oam_manual.py --url <PDF_URL> --isin LU0292107645 --report-date 2024-12-31")
        print("  python test_oam_manual.py --file <PDF_PATH> --isin LU0292107645 --report-date 2024-12-31")
        sys.exit(1)

