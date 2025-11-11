# SEC Form N-PORT ETF Holdings Ingestion Pipeline

## Overview

This pipeline automatically discovers, downloads, and parses **SEC Form N-PORT filings** to extract point-in-time ETF holdings data. All data is stored in a file-based system with full lineage tracking.

## Architecture

### Data Flow

```
SEC EDGAR → Discovery → Download → Parse → Enrich → QA → Gold Holdings
              ↓           ↓          ↓        ↓      ↓
           Metadata    Raw XML   Silver   Gold    Reports
```

### Directory Structure

```
/data
  /raw                         # Raw downloaded SEC filings
    /sec
      /cik=<CIK>
        /accession=<ACCESSION>
          /as_of=<DATE>
            /<SHA256>.xml      # Raw XML filing
            /metadata.json     # Download metadata
  
  /pipeline
    /silver_holdings           # Parsed holdings (raw structure)
      /fund_id=<ID>
        /as_of=<DATE>
          /version=<N>.csv
    
    /gold_holdings             # Enriched holdings (analysis-ready)
      /fund_id=<ID>
        /as_of=<DATE>
          /version=<N>
            /holdings.csv
    
    fund_registry.yaml         # Fund configuration
  
  /qa                          # Quality assurance reports
    /fund_id=<ID>
      /as_of=<DATE>
        /qa_report.json
```

## Components

### 1. `nport_discovery.py`
Discovers N-PORT filings from SEC EDGAR for a given CIK.

**Features:**
- Queries SEC submissions API
- Filters for NPORT-P and NPORT-EX forms
- Date range filtering
- Resolves actual XML instance documents using EDGAR `index.json` manifests

### 2. `nport_download.py`
Downloads filings with polite rate limiting and retry logic.

**Features:**
- 150ms delay between requests
- Exponential backoff retry (3 attempts)
- SHA256 hash computation
- Metadata tracking

### 3. `nport_parser.py`
Parses N-PORT XML to extract holdings data.

**Extracted Fields:**
- `instrument_name_raw` - Security name
- `cusip` / `isin` - Identifiers
- `balance` - Quantity/shares
- `market_value_local` - Market value
- `currency` - Currency code
- `category_raw` - Asset category
- `country_raw` - Country code
- `issuer_name` - Issuer
- `derivative_flag` - Derivative indicator
- `maturity` / `coupon` - Fixed income attributes

### 4. `nport_enrichment.py`
Enriches parsed data to analysis-ready format.

**Enrichment Steps:**
1. **ISIN Resolution** - Resolves ISINs from CUSIP when missing
2. **Weight Calculation** - Computes position weights as % of total
3. **Normalization** - Standardizes country codes, asset classes, sectors

### 5. `nport_qa.py`
Validates data quality and generates reports.

**Quality Checks:**
- Weight sum validation (99.5% - 100.5%)
- Identifier coverage (≥98%)
- Top 10 concentration calculation
- Data completeness verification

### 6. `ingest_nport.py`
Main orchestration script.

## Configuration

### Fund Registry (`fund_registry.yaml`)

```yaml
funds:
  SPY:
    fund_id: SPY
    cik: "0000884394"           # SEC Central Index Key
    series_id: "S000000593"     # Series ID (optional)
    class_id: "C000000664"      # Class ID (optional)
    issuer: State Street
    name: SPDR S&P 500 ETF Trust
    domicile: US
    share_class_isin: US78462F1030
    gold_path: fund_id=SPY
    freshness_days: 30          # Re-fetch after 30 days
    tickers:
      - SPY
```

## Usage

### Basic Ingestion

```bash
# Ingest latest N-PORT filing for SPY
python src/pipeline/ingest_nport.py --fund SPY

# Force re-ingestion even if fresh data exists
python src/pipeline/ingest_nport.py --fund SPY --force

# Backfill historical data
python src/pipeline/ingest_nport.py --fund SPY --date 2024-09-30
```

## Verification Checklist

Follow these steps to validate that discovery, download, parsing, enrichment, and QA all succeed for a real-world filing such as SPY:

1. **Fetch a known-good filing**
   ```bash
   python src/pipeline/ingest_nport.py --fund SPY --date 2024-03-31 --force
   ```
   This runs the full pipeline and forces a redownload of the targeted quarter, ensuring discovery resolves the true XML instance document.

2. **Confirm raw artifacts**
   - Check `data/raw/sec/cik=0000884394/` for a subdirectory named after the accession number (with dashes) containing the XML file rather than `primary_doc.xml`.
   - Inspect `metadata.json` for the `downloaded_url` field pointing at an `nport-p*.xml` asset.

3. **Inspect parsed holdings**
   - Silver output should contain roughly 500 rows for SPY in `data/pipeline/silver_holdings/fund_id=SPY/`.
   - Gold output should mirror the same count with calculated weights.

4. **Review QA report**
   - Open `data/qa/fund_id=SPY/<as_of>/qa_report.json` and ensure weight-sum and identifier coverage checks report success.

If any step fails—especially if the raw XML is missing or malformed—rerun the ingestion with `--force` and consult the logs under `logs/nport_ingest.log`.

### From Python

```python
from pipeline.ingest_nport import NPORTIngestionPipeline

pipeline = NPORTIngestionPipeline()
success = pipeline.ingest_fund('SPY', force=True)
```

## Data Schema

### Silver Holdings (parsed XML)

| Column | Type | Description |
|--------|------|-------------|
| `as_of` | date | Report date |
| `fund_id` | string | Fund identifier |
| `instrument_name_raw` | string | Security name (raw) |
| `cusip` | string | CUSIP identifier |
| `isin` | string | ISIN identifier |
| `balance` | float | Quantity/shares |
| `market_value_local` | float | Market value |
| `currency` | string | Currency code |
| `category_raw` | string | Asset category (raw) |
| `country_raw` | string | Country (raw) |
| `derivative_flag` | boolean | Is derivative |
| `issuer_name` | string | Issuer name |
| `source_url` | string | Source filing URL |
| `parse_hash` | string | Parse version hash |

### Gold Holdings (enriched)

Additional columns:
- `instrument_isin` - Resolved ISIN
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
  "fund_id": "SPY",
  "as_of": "2025-06-30",
  "n_positions": 503,
  "weight_sum": 100.02,
  "unresolved_ids": 4,
  "unresolved_pct": 0.8,
  "top10_concentration": 27.4,
  "top10_holdings": [
    {"name": "Apple Inc", "isin": "US0378331005", "weight_pct": 7.2},
    ...
  ],
  "checks_passed": [
    "Weight sum OK: 100.02%",
    "Identifier coverage OK: 99.2%"
  ],
  "checks_failed": [],
  "status": "pass"
}
```

## Known Limitations

### Current State

1. **XML File Discovery** - The SEC does not provide a simple API to list all files in a filing. The current implementation attempts to parse the filing directory HTML, but this may not always work. Some filings use transformed/rendered XML (XSLT) rather than raw XML.

2. **Alternative Approach Needed** - For robust production use, consider:
   - Using SEC's quarterly bulk N-PORT data sets (ZIP files) from DERA
   - Manual specification of XML file URLs
   - Using third-party data providers

3. **ISIN Resolution** - CUSIP-to-ISIN mapping requires external reference data (not included).

4. **Sector Classification** - Sector enrichment requires external data source or API.

### Workarounds

For immediate testing, you can:

1. **Manual Download**: Download N-PORT XML files manually and place them in the raw directory structure
2. **Use Bulk Data**: Download SEC's quarterly NPORT datasets and extract the relevant files
3. **Third-party APIs**: Use financial data APIs (Bloomberg, Refinitiv, etc.) as alternative sources

## Testing

### Test SPY Holdings Extraction

```bash
# Run full pipeline
python src/pipeline/ingest_nport.py --fund SPY

# Check results
ls -la data/pipeline/gold_holdings/fund_id=SPY/

# View QA report
cat data/qa/fund_id=SPY/as_of=*/qa_report.json | python -m json.tool
```

### Expected Output for SPY

- **Holdings Count**: ~500-505 (S&P 500 components)
- **Weight Sum**: 99.5% - 100.5%
- **Top Holdings**: AAPL, MSFT, GOOGL, AMZN, etc.

## Freshness Logic

The pipeline implements intelligent caching:

1. Check for existing gold holdings
2. If latest `as_of` date is < `freshness_days` old, reuse existing data
3. Otherwise, discover and fetch new filings
4. Backfill requests (`--date`) always fetch regardless of freshness

## Development

### Adding New Funds

1. Find the fund's CIK on SEC EDGAR
2. Add entry to `fund_registry.yaml`
3. Run ingestion: `python ingest_nport.py --fund <FUND_ID>`

### Extending Enrichment

Modify `nport_enrichment.py` to add:
- Custom ISIN resolution
- Sector classification via API
- Currency conversion
- Custom normalizations

## References

- **SEC Form N-PORT Data Sets**: https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets
- **SEC EDGAR API**: https://www.sec.gov/developer
- **N-PORT Filing Structure**: https://www.sec.gov/files/form-nport-data-dictionary.pdf

## Troubleshooting

### "No holdings extracted from filing"

**Cause**: Downloaded file is HTML rendering, not raw XML

**Solutions**:
1. Check if the file at `data/raw/sec/.../.../.xml` is actually XML or HTML
2. Manually locate the raw XML file in the SEC filing
3. Use SEC's quarterly bulk data sets instead

### "Failed to parse XML: mismatched tag"

**Cause**: Malformed XML or HTML content

**Solution**: Verify you're downloading the correct XML instance document, not the XSLT-rendered version

### "No N-PORT filings found"

**Causes**:
- CIK not registered with SEC for N-PORT
- Date range doesn't include any filings
- Fund may file under different form type

**Solution**: Verify CIK and check SEC EDGAR manually

## Future Enhancements

1. **Bulk Data Integration** - Direct integration with SEC DERA quarterly ZIP files
2. **Parallel Processing** - Multi-threaded download and parsing
3. **Delta Detection** - Incremental updates when holdings change minimally
4. **Sector Enrichment** - Integration with sector classification APIs
5. **FX Conversion** - Real-time currency conversion
6. **Derivatives Expansion** - Enhanced derivative position parsing

