"""Manual test script for BDIF pipeline with a PDF file.

This allows testing the parser, enrichment, and QA modules
even when discovery doesn't find reports in the API.
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.bdif_parser import BDIFParser
from pipeline.bdif_enrichment import BDIFEnrichment
from pipeline.bdif_qa import BDIFQualityAssurance


def test_with_pdf(pdf_path: str, fund_id: str = "FR0013380607"):
    """Test the BDIF pipeline with a manually provided PDF.
    
    Args:
        pdf_path: Path to BDIF PDF file
        fund_id: Fund identifier
    """
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"Error: PDF file not found: {pdf_path}")
        return False
    
    print("=" * 60)
    print(f"Testing BDIF Pipeline with PDF: {pdf_path}")
    print("=" * 60)
    
    # Step 1: Parse PDF
    print("\n[1/4] Parsing PDF...")
    parser = BDIFParser()
    holdings, metadata = parser.parse_report(pdf_file, fund_id)
    
    if not holdings:
        print("Warning: No holdings extracted from PDF")
        print("This might be normal if the PDF doesn't contain a holdings table")
        return False
    
    print(f"✓ Extracted {len(holdings)} holdings")
    print(f"  As of date: {metadata.get('as_of', 'N/A')}")
    
    # Step 2: Convert to DataFrame
    print("\n[2/4] Converting to DataFrame...")
    silver_df = parser.to_dataframe(holdings)
    print(f"✓ Created DataFrame with {len(silver_df)} rows")
    print(f"  Columns: {list(silver_df.columns)}")
    
    # Step 3: Enrich
    print("\n[3/4] Enriching holdings...")
    enrichment = BDIFEnrichment()
    gold_df = enrichment.enrich_holdings(silver_df)
    print(f"✓ Enriched to {len(gold_df)} rows")
    
    # Show sample
    if len(gold_df) > 0:
        print("\nSample holdings:")
        print(gold_df[["designation", "isin", "weight_pct", "market_value_eur"]].head().to_string())
    
    # Step 4: QA
    print("\n[4/4] Running QA validation...")
    qa_dir = Path(__file__).parent.parent.parent / "data" / "qa"
    qa = BDIFQualityAssurance(qa_dir)
    as_of = metadata.get("as_of", date.today().strftime("%Y-%m-%d"))
    qa_result = qa.validate_holdings(gold_df, fund_id, as_of)
    
    print(f"✓ QA Status: {qa_result.status.upper()}")
    print(f"  Positions: {qa_result.n_positions}")
    print(f"  Weight sum: {qa_result.weight_sum:.2f}%")
    print(f"  Missing ISINs: {qa_result.missing_isin}")
    print(f"  Top 10 concentration: {qa_result.top10_concentration:.2f}%")
    
    if qa_result.checks_passed:
        print("\n  Passed checks:")
        for check in qa_result.checks_passed:
            print(f"    ✓ {check}")
    
    if qa_result.checks_failed:
        print("\n  Failed checks:")
        for check in qa_result.checks_failed:
            print(f"    ✗ {check}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    
    return qa_result.status == "pass"


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python test_bdif_manual.py <path_to_pdf> [fund_id]")
        print("\nExample:")
        print("  python test_bdif_manual.py /path/to/bdif_report.pdf FR0013380607")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    fund_id = sys.argv[2] if len(sys.argv) > 2 else "FR0013380607"
    
    success = test_with_pdf(pdf_path, fund_id)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
