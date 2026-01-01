# BDIF Pipeline Documentation

## Overview

The BDIF (Base des Décisions et Informations Financières) pipeline extracts holdings data from French UCITS ETF reports published by the AMF (Autorité des Marchés Financiers).

## Current Status

### ✅ Working Components

1. **Discovery Module** (`bdif_discovery.py`)
   - Connects to info-financiere.gouv.fr API
   - Searches for reports by ISIN
   - Handles API errors gracefully
   - Includes debug mode for troubleshooting

2. **Parser Module** (`bdif_parser.py`)
   - Extracts holdings from BDIF PDF reports
   - Parses tables containing portfolio composition
   - Extracts ISINs, quantities, values, and weights
   - Handles French date formats

3. **Enrichment Module** (`bdif_enrichment.py`)
   - Normalizes ISINs
   - Computes weights if missing
   - Adds country information

4. **QA Module** (`bdif_qa.py`)
   - Validates weight sums
   - Checks ISIN coverage
   - Reports top 10 concentration
   - Generates QA reports

### ⚠️ Known Limitations

**API Access Issue**: The `info-financiere.gouv.fr` API appears to be primarily for listed companies, not UCITS funds. BDIF reports for UCITS ETFs may need to be accessed through:

1. **BDIF Website**: https://bdif.amf-france.org
   - Direct website access may be required
   - Reports may need to be downloaded manually

2. **Alternative API**: There may be a different API endpoint or dataset specifically for UCITS funds

3. **GECO Platform**: The AMF has launched a new platform (GECO) for investment fund data - this may be the correct source

## Usage

### Standard Ingestion

```bash
python src/pipeline/ingest_bdif.py --fund FR0013380607
```

### With Debug Output

```python
from pipeline.bdif_discovery import BDIFDiscovery

discovery = BDIFDiscovery()
reports = discovery.discover_reports('FR0013380607', debug=True)
```

### Manual PDF Testing

If you have a BDIF PDF file, you can test the parser directly:

```bash
python src/pipeline/test_bdif_manual.py /path/to/bdif_report.pdf FR0013380607
```

## Testing

Run the test suite:

```bash
python src/pipeline/test_bdif.py
```

This will:
- Test discovery with debug output
- Verify parser structure
- Verify enrichment structure
- Verify QA structure

## Field Mappings

The discovery module uses the following API field mappings:

| Purpose | API Field |
|---------|-----------|
| PDF URL | `url_de_recuperation` |
| ISIN | `identificationsociete_iso_cd_isi` |
| Date | `uin_dat_amf`, `uin_dat_mar`, `informationdeposee_inf_dat_emt` |
| Title | `informationdeposee_inf_tit_inf` |
| Document Type | `type_d_information`, `sous_type_d_information` |
| Record ID | `recordid` |

## Document Type Codes

The pipeline looks for periodic financial reports. Document types that may indicate holdings reports:

- Reports containing "périodique" or "periodic"
- Reports with "rapport" or "report" in subtype
- Reports mentioning "composition" or "actif" or "portefeuille"

Note: The exact document codes (A.1.1, A.1.2) referenced in the code may not exist in the API response format.

## Next Steps

1. **Verify BDIF Access Method**
   - Check if BDIF website has an API
   - Investigate GECO platform for UCITS data
   - Contact AMF for API access information

2. **Test with Real PDF**
   - Download a BDIF report manually from bdif.amf-france.org
   - Test the parser with `test_bdif_manual.py`
   - Verify holdings extraction works correctly

3. **Alternative Data Sources**
   - Consider using OAM (Official Appointed Mechanism) for Luxembourg-domiciled funds
   - Check if French UCITS publish holdings through other channels

## Registry Configuration

French ETFs should be registered in `data/pipeline/fund_registry.yaml`:

```yaml
FR0013380607:
  fund_id: FR0013380607
  share_class_isin: FR0013380607
  domicile: FR
  name: Amundi CAC 40 UCITS ETF Acc
  issuer: Amundi
  tickers:
    - CA40.PA
  isin: FR0013380607
  jurisdiction: FR
  freshness_days: 185
  gold_path: fund_id=FR0013380607
```

## Troubleshooting

### No Reports Found

If discovery returns 0 reports:

1. Check if the ISIN is correct
2. Verify the ETF has published BDIF reports
3. Try accessing BDIF website directly
4. Check if reports are in a different dataset

### Parser Issues

If parser doesn't extract holdings:

1. Verify PDF contains a holdings table
2. Check if table format matches expected structure
3. Review PDF text extraction (may need OCR for scanned PDFs)

### API Errors

If you get 400/500 errors:

1. Check API endpoint is still valid
2. Verify dataset name hasn't changed
3. Check rate limiting (code includes throttling)

## Code Structure

```
src/pipeline/
├── bdif_discovery.py      # API discovery
├── bdif_download.py        # PDF download
├── bdif_parser.py          # PDF parsing
├── bdif_enrichment.py      # Data enrichment
├── bdif_qa.py              # Quality assurance
├── ingest_bdif.py         # Main ingestion pipeline
├── test_bdif.py           # Automated tests
└── test_bdif_manual.py    # Manual PDF testing
```
