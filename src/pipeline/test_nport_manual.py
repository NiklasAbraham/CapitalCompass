"""Manual test script for N-PORT ingestion with direct file URLs.

This script allows testing the N-PORT pipeline with manually specified URLs
or local files, bypassing the discovery mechanism.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.nport_download import NPORTDownloader
from pipeline.nport_parser import NPORTParser
from pipeline.nport_enrichment import NPORTEnrichment
from pipeline.nport_qa import NPORTQualityAssurance


def test_with_url(
    fund_id: str = "SPY",
    cik: str = "0000884394",
    url: str = "",
    as_of: str = "",
):
    """Test ingestion with a manually specified URL.
    
    Args:
        fund_id: Fund identifier
        cik: CIK
        url: Direct URL to N-PORT XML file
        as_of: Report date (YYYY-MM-DD)
    """
    # Set up directories
    project_root = Path(__file__).parent.parent.parent
    raw_dir = project_root / "data" / "raw"
    silver_dir = project_root / "data" / "pipeline" / "silver_holdings"
    gold_dir = project_root / "data" / "pipeline" / "gold_holdings"
    qa_dir = project_root / "data" / "qa"
    
    for directory in [raw_dir, silver_dir, gold_dir, qa_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    
    # Derive accession from URL if possible
    accession = url.split('/')[-2] if '/' in url else "manual"
    if not as_of:
        as_of = datetime.now().strftime("%Y-%m-%d")
    
    print(f"\nManual N-PORT Test")
    print(f"{'='*60}")
    print(f"Fund ID: {fund_id}")
    print(f"CIK: {cik}")
    print(f"URL: {url}")
    print(f"As of: {as_of}")
    print(f"{'='*60}\n")
    
    # Download
    downloader = NPORTDownloader(raw_dir)
    xml_path = downloader.download_filing(url, cik, accession, as_of)
    
    if not xml_path or not xml_path.exists():
        print("❌ Download failed")
        return False
    
    print(f"✓ Downloaded to {xml_path}")
    
    # Parse
    parser = NPORTParser()
    holdings, metadata = parser.parse_filing(xml_path, fund_id, url)
    
    if not holdings:
        print("❌ No holdings extracted")
        print("\nTip: The URL may point to an HTML rendering instead of raw XML.")
        print("Try finding the actual XML file in the SEC filing directory.")
        return False
    
    print(f"✓ Parsed {len(holdings)} holdings")
    
    # Save silver
    silver_df = parser.to_dataframe(holdings)
    silver_path = silver_dir / f"fund_id={fund_id}" / f"as_of={as_of}"
    silver_path.mkdir(parents=True, exist_ok=True)
    silver_file = silver_path / "version=1.csv"
    silver_df.to_csv(silver_file, index=False)
    print(f"✓ Saved silver: {silver_file}")
    
    # Enrich
    enrichment = NPORTEnrichment()
    gold_df = enrichment.enrich_holdings(silver_df)
    
    # Save gold
    gold_path = gold_dir / f"fund_id={fund_id}" / f"as_of={as_of}" / "version=1"
    gold_path.mkdir(parents=True, exist_ok=True)
    gold_file = gold_path / "holdings.csv"
    gold_df.to_csv(gold_file, index=False)
    print(f"✓ Saved gold: {gold_file}")
    
    # QA
    qa = NPORTQualityAssurance(qa_dir)
    qa_result = qa.validate_holdings(gold_df, fund_id, as_of)
    
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


def test_known_filings():
    """Test with known working N-PORT filings."""
    
    print("Testing N-PORT Ingestion with Known Filings\n")
    
    # Example: Try SPY's latest filing
    # Note: You need to find the actual XML file URL manually
    # The SEC filing page is: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000884394&type=NPORT
    
    test_cases = [
        {
            "fund_id": "SPY",
            "cik": "0000884394",
            # This URL needs to be updated with the actual XML file
            # Format: https://www.sec.gov/Archives/edgar/data/{CIK}/{ACCESSION}/{FILENAME}.xml
            "url": "https://www.sec.gov/Archives/edgar/data/0000884394/000175272425211156/NPORT-P.xml",
            "as_of": "2025-06-30",
        },
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"Test Case {i}/{len(test_cases)}")
        print(f"{'='*60}")
        
        success = test_with_url(**test_case)
        
        if not success:
            print(f"\n⚠ Test case {i} did not complete successfully")
            print("\nNote: N-PORT XML file discovery is complex.")
            print("You may need to manually find the correct XML file URL from:")
            print(f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={test_case['cik']}&type=NPORT")
            print("\nLook for files like 'NPORT-P.xml' or similar (not primary_doc.xml)")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Manual N-PORT testing")
    parser.add_argument("--fund", type=str, default="SPY", help="Fund ID")
    parser.add_argument("--cik", type=str, default="0000884394", help="CIK")
    parser.add_argument("--url", type=str, default="", help="Direct URL to XML file")
    parser.add_argument("--as-of", type=str, default="", help="Report date (YYYY-MM-DD)")
    parser.add_argument("--test-known", action="store_true", help="Run tests with known URLs")
    
    args = parser.parse_args()
    
    if args.test_known:
        test_known_filings()
    elif args.url:
        test_with_url(args.fund, args.cik, args.url, args.as_of)
    else:
        print("Error: Please provide --url or --test-known")
        print("\nUsage:")
        print("  python test_nport_manual.py --url <XML_URL> --fund SPY --as-of 2025-06-30")
        print("  python test_nport_manual.py --test-known")
        sys.exit(1)

