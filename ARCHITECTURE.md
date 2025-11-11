# CapitalCompass Architecture

## Overview

CapitalCompass uses a class-based architecture for handling different asset types. This design provides flexibility, extensibility, and clean separation of concerns.

## Core Components

### 1. Asset Class Hierarchy

Located in `src/core/assets/`:

#### Base Asset Class (`base.py`)
Abstract base class that defines the interface for all financial assets:
- Properties: `ticker`, `units`, `weight`, `price`, `sector`, `name`, `market_value`
- Abstract methods: `fetch_data()`, `get_holdings()`
- Concrete methods: `to_dict()`, `__repr__()`

#### Stock Class (`stock.py`)
Represents individual stocks:
- Uses Yahoo Finance (`yfinance`) for market data
- Fetches price, sector, fundamentals (P/E, dividend yield, etc.)
- Returns `None` for `get_holdings()` (stocks are atomic)

#### ETF Class (`etf.py`)
- Represents Exchange-Traded Funds with deep look-through capability:
- Preferred data source: **Primary holdings pipeline** (issuer CSV/XLSX and SEC N-PORT snapshots stored under `data/pipeline/`)
- Secondary data source: **AlphaVantage** for live holdings when the pipeline lacks coverage
- Final safety net: Yahoo Finance `funds_data` for truncated holdings snapshots
- Automatically excludes money-market and bond funds from look-through (configurable keywords)
- Caches API responses per instance to reduce duplicate network calls
- Enriches metadata using pipeline provenance where available and Yahoo Finance fundamentals otherwise
- Provides performance metrics (YTD return, multi-year averages, expense ratio) via Yahoo Finance

### 2. API Integrations

Located in `src/api/`:

#### AlphaVantage Client (`alpha_vantage.py`)
Provides access to AlphaVantage API:
- **ETF Profile**: `get_etf_profile()` returns detailed holdings data
- **Quote Data**: `get_quote()` for real-time prices
- **Company Overview**: `get_company_overview()` for fundamentals
- Configuration: API key stored in `.env` file (see `.env.example`)

#### Primary Holdings Client (`pipeline/primary_holdings.py`)
Local client that reads deterministic issuer/SEC gold snapshots stored under `data/pipeline/`:
- Resolves ETF tickers to canonical fund identifiers via `fund_registry.yaml`
- Normalises holdings schema (weights, quantities, currencies) with provenance metadata
- Provides helper methods to aggregate country/sector/asset-class exposures directly from gold holdings

### 3. Portfolio Analysis

#### Portfolio Module (`portfolio.py`)
Uses asset classes for portfolio composition analysis:
- `load_portfolio_config()`: Creates Asset objects from JSON
- `fetch_portfolio_data()`: Retrieves market data for all assets
- `analyze_portfolio_with_assets()`: Performs full analysis with ETF look-through
- Supports both unit-based and weight-based portfolios

### 4. Analysis Scripts

#### Simple Portfolio Analysis (`analysis/simple_portfolio_analysis.py`)
Standalone script for current portfolio overview:
- Displays portfolio configuration
- Generates asset allocation charts (PNG)
- Performs ETF look-through via the primary holdings pipeline → AlphaVantage → Yahoo Finance fallbacks
- Shows aggregated exposure (direct + indirect holdings)
- Computes portfolio-level ETF country/sector/asset-class exposures and stores CSV artefacts
- Prints ETF performance metrics

## Data Flow

```
1. Portfolio Config (JSON)
   ↓
2. Asset Objects Created (Stock/ETF)
   ↓
3. Market Data Fetched (Yahoo Finance)
   ↓
4. ETF Holdings & Exposures Retrieved (Primary pipeline → AlphaVantage → Yahoo Finance fallback)
   ↓
5. Analysis, Exposure Aggregation & Visualization
   ↓
6. Results (Charts, DataFrames, Metrics)
```

## Configuration

### Portfolio JSON Schema

```json
[
  {
    "ticker": "URTH",
    "weight": 0.3649,
    "type": "etf"
  },
  {
    "ticker": "AAPL",
    "units": 10,
    "type": "stock"
  }
]
```

**Fields:**
- `ticker` (required): Asset symbol
- `type` (required): "etf" or "stock"
- `weight` (optional): Portfolio weight as decimal (e.g., 0.25 = 25%)
- `units` (optional): Number of shares/units held
- **Note**: Specify either `weight` OR `units`, not both

### Environment Variables

Create a `.env` file in project root containing API credentials. Multiple keys can be added for automatic rotation:

```bash
ALPHAVANTAGE_API_KEY=your_primary_alpha_key
ALPHAVANTAGE_API_KEY_1=your_secondary_alpha_key
```

- AlphaVantage keys: https://www.alphavantage.co/support/#api-key

## Primary Holdings Artifacts

- Location: `data/pipeline/`
  - `fund_registry.yaml` maps tickers to canonical fund identifiers and issuer metadata
  - `gold_holdings/fund_id=…/as_of=YYYY-MM-DD/version=N/holdings.csv` stores deterministic, provenance-rich snapshots
- Access: `PrimaryHoldingsClient` normalises weights, symbols, and metadata and is used automatically when
  `holdings_source="primary"` or the global override requests it
- Semantics: files preserve as-filed weights, currencies, and lineage fields (`source`, `source_url`, `source_doc_id`)
  allowing deterministic replays and auditability

## ETF Data Strategy

1. **Holdings Priority**
   - **Primary pipeline**: reads deterministic gold snapshots (`data/pipeline/gold_holdings/fund_id=…/as_of=…/version=…`) via `PrimaryHoldingsClient`
   - **AlphaVantage** (`ETF_PROFILE`) when a pipeline snapshot is missing
   - **Yahoo Finance** (`funds_data.top_holdings`) as the final fallback for truncated snapshots
   - Money-market and bond-style ETFs are still excluded automatically using keyword heuristics

2. **Exposure Priority**
   - Primary pipeline holdings aggregate to portfolio-level country / sector / asset-class exposures when metadata exists
   - Exposure gaps are reported so new pipeline snapshots can be prioritised
   - Weight-only portfolios cache aggregated exposure CSVs using a hash signature to avoid redundant API calls

3. **Metadata Augmentation**
   - Pipeline metadata (issuer, fund ID, as-of, version, source document) is attached to each ETF instance when available
   - Yahoo Finance supplements performance statistics (YTD, 3Y, 5Y) and fund descriptors

## Future Enhancements

### Planned Features
- **Historical Holdings**: CSV-based monthly holdings data for backtesting
- **Performance Attribution**: Breakdown of returns by holding
- **Risk Analytics**: VaR, CVaR, stress testing
- **Optimization**: Portfolio optimization based on look-through data

### Extensibility
The asset class architecture makes it easy to add new asset types:
- `Bond`: Individual bonds with yield curves
- `Option`: Derivatives with Greeks
- `Cryptocurrency`: Digital assets
- `RealEstate`: REITs or direct property

Simply extend the `Asset` base class and implement `fetch_data()` and `get_holdings()`.

## Best Practices

1. **API Rate Limits**: AlphaVantage free tier allows 25 calls/day. Keys rotate across available values—add multiple keys in `.env` when possible.

2. **Portfolio Updates**: Run `simple_portfolio_analysis.py` to get current snapshot. For daily tracking, schedule runs outside trading hours.

3. **Data Quality**: The issuer/SEC pipeline is authoritative but only covers registered funds; AlphaVantage bridges gaps. Yahoo Finance is a last resort and may omit many international funds.

4. **Configuration Management**: Use separate JSON files for different portfolios (`config_personal.json`, `config_retirement.json`, etc.).

## Troubleshooting

### "AlphaVantage API key not found"
- Confirm fallback keys (`ALPHAVANTAGE_API_KEY`, `ALPHAVANTAGE_API_KEY_1`, …) are present
- Remove extraneous whitespace or quote characters

### "No holdings data for [ETF]"
- Confirm the ticker is mapped in `data/pipeline/fund_registry.yaml` when using the primary pipeline
- Ensure your AlphaVantage key is valid; the client falls back to Yahoo Finance when API data is unavailable
- European or synthetic ETFs may not be covered by either source—Yahoo Finance fallback will attempt a truncated snapshot
- Money market / bond ETFs are intentionally excluded from look-through to avoid spurious exposures

### "No country/sector/asset allocation data for [ETF]"
- Many niche or synthetic funds do not publish allocation breakdowns via free APIs
- Check console output for the list of ETFs missing exposure data; allocations for other funds still aggregate correctly
- Cached CSVs in `outputs/cache/` can be deleted to force a fresh retry if API keys have changed

### Import Errors
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Activate the correct conda environment: `conda activate capital`
- Check Python path includes project root

## Module Structure

```
src/
├── api/
│   ├── __init__.py
│   └── alpha_vantage.py      # AlphaVantage API client
├── core/
│   ├── assets/
│   │   ├── __init__.py
│   │   ├── base.py           # Abstract Asset class
│   │   ├── stock.py          # Stock implementation
│   │   └── etf.py            # ETF implementation
│   ├── portfolio.py          # Asset-based portfolio analysis
│   ├── market_sim.py         # Index simulation
│   ├── etf_analyzer.py       # ETF utilities (legacy)
│   └── performance_metrics.py # Performance calculations
├── analysis/
│   ├── simple_portfolio_analysis.py      # Asset-based script
└── config.py                 # Configuration constants
```

