# European UCITS OAM Holdings Ingestion Pipeline

## Overview

This pipeline automatically discovers, downloads, and parses **European UCITS ETF holdings** from **Officially Appointed Mechanism (OAM)** portals. The system supports Luxembourg (LuxSE) and Germany (Bundesanzeiger/Fondsdata) domiciled funds, extracting holdings from annual and semi-annual reports published on official regulatory portals.

## Architecture

### Data Flow

```
OAM Portal → Discovery → Download → Parse → Enrich → QA → Gold Holdings
              ↓           ↓          ↓        ↓      ↓
           Metadata    Raw PDF   Silver   Gold    Reports
```

### Directory Structure

```
/data
  /raw                         # Raw downloaded PDF reports
    /oam=LuxSE/
      /isin=<ISIN>/
        /report_date=<DATE>/
          /<SHA256>.pdf        # Raw PDF report
          /metadata.json       # Download metadata
  
  /pipeline
    /silver                    # Parsed holdings (raw structure)
      /isin=<ISIN>/
        /report_date=<DATE>/
          /version=<N>.csv
    
    /gold_holdings             # Enriched holdings (analysis-ready)
      /isin=<ISIN>/
        /report_date=<DATE>/
          /version=<N>/
            /holdings.csv
    
    fund_registry.yaml         # Fund configuration
  
  /qa                          # Quality assurance reports
    /isin=<ISIN>/
      /report_date=<DATE>/
        /qa_report.json
```

## Components

### 1. `oam_discovery.py`
Discovers UCITS reports from OAM portals.

**Features:**
- LuxSE OAM search by ISIN and year
- Bundesanzeiger/Fondsdata navigation
- Date range filtering
- Report type detection (annual, semi-annual, monthly)

### 2. `oam_download.py`
Downloads PDF reports with polite rate limiting and retry logic.

**Features:**
- 1 second delay between requests
- Exponential backoff retry (3 attempts)
- SHA256 hash computation
- PDF validation
- Metadata tracking

### 3. `oam_parser.py`
Parses PDF reports to extract holdings data.

**Extracted Fields:**
- `instrument_name_raw` - Security name
- `isin_raw` / `instrument_isin` - ISIN identifiers
- `quantity` - Quantity/shares
- `market_value_local` - Market value
- `currency` - Currency code
- `country_raw` - Country code
- `sector_raw` - Sector classification
- `section` - Asset section (Equities, Bonds, Derivatives, Cash)

**Parsing Strategy:**
- Uses `pdfplumber` for table extraction
- Detects holdings tables by header keywords
- Falls back to text-based extraction if tables not found
- Handles multi-section reports (equities, bonds, derivatives)

### 4. `oam_enrichment.py`
Enriches parsed data to analysis-ready format.

**Enrichment Steps:**
1. **ISIN Resolution** - Validates and normalizes ISIN format
2. **Weight Calculation** - Computes position weights as % of total
3. **Normalization** - Standardizes country codes, asset classes, sectors

### 5. `oam_qa.py`
Validates data quality and generates reports.

**Quality Checks:**
- Weight sum validation (99.5% - 100.5%)
- Identifier coverage (≥95%)
- Top 10 concentration calculation
- Data completeness verification

### 6. `ingest_oam.py`
Main orchestration script.

### 7. Integration with `auto_snapshot.py`
The existing `auto_snapshot.py` can be extended to support OAM ingestion when a fund entry includes `isin` and `oam` fields but no `cik`.

## Configuration

### Fund Registry (`fund_registry.yaml`)

The registry supports both list and dictionary formats. For European funds, use the list format:

```yaml
funds:
  - isin: LU0292107645
    domicile: LU
    oam: LuxSE
    freshness_days: 210          # Semi-annual cadence (+ buffer)
    issuer: iShares
    name: iShares Core MSCI World UCITS ETF
    tickers:
      - SWDA.L
      - EUNL.DE

  - isin: DE000ETFL123
    domicile: DE
    oam: Bundesanzeiger
    freshness_days: 210
    issuer: DWS
    name: Example German ETF
    tickers:
      - ETFL.DE
```

**Required fields:**
- `isin` - ISIN identifier (12 characters)
- `domicile` - Country code (LU or DE)
- `oam` - OAM name (LuxSE or Bundesanzeiger)

**Optional fields:**
- `freshness_days` - Days before re-fetching (default: 210)
- `issuer` - Fund issuer name
- `name` - Fund name
- `tickers` - List of trading tickers

## Usage

### Basic Ingestion

```bash
# Ingest latest OAM report for a Luxembourg fund
python src/pipeline/ingest_oam.py --isin LU0292107645

# Force re-ingestion even if fresh data exists
python src/pipeline/ingest_oam.py --isin LU0292107645 --force

# Backfill historical data
python src/pipeline/ingest_oam.py --isin LU0292107645 --date 2024-12-31
```

### From Python

```python
from pipeline.ingest_oam import OAMIngestionPipeline

pipeline = OAMIngestionPipeline()
success = pipeline.ingest_fund('LU0292107645', force=True)
```

### Manual Testing

```bash
# Test with a direct PDF URL
python src/pipeline/test_oam_manual.py --url <PDF_URL> --isin LU0292107645 --report-date 2024-12-31

# Test with a local PDF file
python src/pipeline/test_oam_manual.py --file <PDF_PATH> --isin LU0292107645 --report-date 2024-12-31
```

## Data Schema

### Silver Holdings (parsed PDF)

| Column | Type | Description |
|--------|------|-------------|
| `report_date` | date | Report date |
| `isin` | string | Fund ISIN |
| `instrument_name_raw` | string | Security name (raw) |
| `isin_raw` | string | Security ISIN |
| `currency` | string | Currency code |
| `quantity` | float | Quantity/shares |
| `market_value_local` | float | Market value |
| `market_price` | float | Market price (optional) |
| `country_raw` | string | Country (raw) |
| `sector_raw` | string | Sector (raw) |
| `section` | string | Asset section |
| `source_url` | string | Source report URL |
| `parse_hash` | string | Parse version hash |

### Gold Holdings (enriched)

Additional columns:
- `instrument_isin` - Validated ISIN
- `weight_pct` - Position weight (%)
- `market_value_eur` - Market value (normalized)
- `country` - ISO country code
- `asset_class` - Standardized asset class
- `sector` - Sector classification
- `instrument_name` - Cleaned name

## Quality Assurance

QA reports are generated in JSON format:

```json
{
  "isin": "LU0292107645",
  "report_date": "2024-12-31",
  "n_positions": 150,
  "weight_sum": 100.02,
  "unresolved_ids": 5,
  "unresolved_pct": 3.3,
  "top10_concentration": 28.5,
  "top10_holdings": [
    {"name": "Apple Inc", "isin": "US0378331005", "weight_pct": 4.2},
    ...
  ],
  "checks_passed": [
    "Weight sum OK: 100.02%",
    "Identifier coverage OK: 96.7%"
  ],
  "checks_failed": [],
  "status": "pass"
}
```

## Known Limitations

### Current State

1. **PDF Parsing Complexity** - PDF table extraction is inherently fragile. Different report formats may require manual adjustment of parsing logic.

2. **Discovery Reliability** - OAM portals may use JavaScript-rendered content or require form submissions that are difficult to automate. The current implementation provides a framework but may need refinement for specific portals.

3. **Report Frequency** - Unlike N-PORT (monthly), UCITS reports are typically semi-annual or annual. This means less frequent data updates.

4. **Language Support** - Reports may be in German, French, or English. The parser attempts to handle common keywords but may need language-specific adjustments.

5. **Table Format Variations** - Holdings tables vary significantly between issuers. The parser uses heuristics but may miss some formats.

### Workarounds

For immediate testing, you can:

1. **Manual Download**: Download PDF reports manually and place them in the raw directory structure
2. **Direct URL Testing**: Use `test_oam_manual.py` with direct PDF URLs
3. **Local File Testing**: Use `test_oam_manual.py` with local PDF files

## Testing

### Unit Tests

```bash
# Run all OAM tests
pytest src/pipeline/test_oam.py -v

# Run specific test class
pytest src/pipeline/test_oam.py::TestOAMDiscovery -v
```

### Integration Test

```bash
# Test full pipeline with mocked dependencies
pytest src/pipeline/test_oam.py::test_integration_mock -v
```

### Manual Test with Real Data

```bash
# Find a real UCITS report PDF URL and test
python src/pipeline/test_oam_manual.py --url <PDF_URL> --isin LU0292107645
```

## Freshness Logic

The pipeline implements intelligent caching:

1. Check for existing gold holdings
2. If latest `report_date` is < `freshness_days` old, reuse existing data
3. Otherwise, discover and fetch new reports
4. Backfill requests (`--date`) always fetch regardless of freshness

## Development

### Adding New Funds

1. Find the fund's ISIN and domicile
2. Determine the OAM (LuxSE for LU, Bundesanzeiger for DE)
3. Add entry to `fund_registry.yaml`
4. Run ingestion: `python ingest_oam.py --isin <ISIN>`

### Extending Enrichment

Modify `oam_enrichment.py` to add:
- Custom ISIN resolution from external sources
- Sector classification via API
- Currency conversion
- Custom normalizations

### Improving PDF Parsing

Modify `oam_parser.py` to:
- Add new table format patterns
- Improve section detection
- Handle multi-language reports
- Extract additional metadata fields

## Dependencies

Required packages:
- `pdfplumber` - PDF parsing and table extraction
- `beautifulsoup4` - HTML parsing for discovery
- `requests` - HTTP requests
- `pandas` - Data manipulation
- `pyyaml` - Registry configuration

Install with:
```bash
pip install pdfplumber beautifulsoup4 requests pandas pyyaml
```

## References

- **LuxSE OAM**: https://www.luxse.com/issuer-services-overview/oam
- **Bundesanzeiger Fondsdata**: https://www.bundesanzeiger.de/pub/de/fondsdata
- **UCITS Directive**: https://www.esma.europa.eu/press-news/esma-news/esma-publishes-guidelines-ucits
- **PwC Luxembourg Fund Reporting Guide**: https://www.pwc.lu/en/asset-management/docs/pwc-lux-gaap.pdf

## Troubleshooting

### "No holdings extracted from PDF"

**Causes:**
- PDF does not contain a recognizable holdings table
- Table format is not supported by the parser
- PDF is encrypted or corrupted

**Solutions:**
1. Open the PDF manually and verify it contains a holdings table
2. Check the table format and adjust parser patterns if needed
3. Try using `test_oam_manual.py` with the PDF to debug

### "Failed to discover reports"

**Causes:**
- OAM portal structure changed
- ISIN not found in OAM database
- Portal requires JavaScript rendering

**Solutions:**
1. Verify the ISIN is correct and the fund is registered
2. Check the OAM portal manually
3. Use manual download and `test_oam_manual.py` as workaround

### "PDF parsing error"

**Causes:**
- `pdfplumber` not installed
- PDF is corrupted
- PDF uses unsupported features

**Solutions:**
1. Install pdfplumber: `pip install pdfplumber`
2. Verify PDF opens in a PDF viewer
3. Try a different PDF or report version

## Future Enhancements

1. **Additional OAMs** - Support for other EU countries (Ireland, France, etc.)
2. **Improved Discovery** - Selenium-based discovery for JavaScript-rendered portals
3. **OCR Fallback** - Use OCR for scanned PDFs
4. **Multi-language Support** - Enhanced language detection and keyword mapping
5. **Table Format Learning** - Machine learning for table format detection
6. **Incremental Updates** - Track changes between reports

