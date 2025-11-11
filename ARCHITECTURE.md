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
Represents Exchange-Traded Funds with deep look-through capability:
- Primary data source: **Financial Modeling Prep (FMP)** for holdings, country, sector, and asset allocation data
- Secondary data source: **AlphaVantage** for holdings if FMP is unavailable or rate-limited
- Final fallback: Yahoo Finance `funds_data` for basic holdings snapshots
- Automatically excludes money-market and bond funds from look-through (configurable keywords)
- Caches API responses per instance to reduce duplicate network calls
- Enriches metadata (issuer, AUM, expense ratio) via FMP overview data
- Provides performance metrics (YTD return, multi-year averages, expense ratio) via Yahoo Finance

### 2. API Integrations

Located in `src/api/`:

#### AlphaVantage Client (`alpha_vantage.py`)
Provides access to AlphaVantage API:
- **ETF Profile**: `get_etf_profile()` returns detailed holdings data
- **Quote Data**: `get_quote()` for real-time prices
- **Company Overview**: `get_company_overview()` for fundamentals
- Configuration: API key stored in `.env` file (see `.env.example`)

#### Financial Modeling Prep Client (`fmp.py`)
Provides access to FMP’s funds, quote, and profile endpoints with key rotation and endpoint fallbacks:
- **ETF Holdings**: `get_etf_holdings()` (`stable/etf/holdings` → `api/v3/etf/holdings`)
- **Country Allocation**: `get_etf_country_weights()` (`stable/etf/country-weightings` → `api/v3/etf-country-weightings`)
- **Sector Allocation**: `get_etf_sector_weights()` (`stable/etf/sector-weightings` → `api/v3/etf-sector-weightings`)
- **Asset Allocation**: `get_etf_asset_allocation()` (`stable/etf/asset-allocation` → `api/v3/etf-asset-allocation`)
- **ETF Overview**: `get_etf_overview()` combines information from `stable/etf/information`, `stable/etf/profile`, and `api/v3/etf-profile`
- **Quotes / Profiles**: `get_quote()` and `get_company_profile()` reuse the broader equity endpoints (`stable/quote`, `stable/profile`)
- All responses log the final URL and key index; `Information` / `Note` rate-limit messages trigger automatic key rotation

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
- Performs ETF look-through via FMP → AlphaVantage → Yahoo Finance fallbacks
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
4. ETF Holdings & Exposures Retrieved (FMP → AlphaVantage → Yahoo Finance fallback)
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
# Financial Modeling Prep (primary ETF data source)
FMP_API_KEY=your_primary_fmp_key
FMP_API_KEY_1=your_secondary_fmp_key

# AlphaVantage (fallback ETF data source)
ALPHAVANTAGE_API_KEY=your_primary_alpha_key
ALPHAVANTAGE_API_KEY_1=your_secondary_alpha_key
```

- FMP keys: https://site.financialmodelingprep.com/
- AlphaVantage keys: https://www.alphavantage.co/support/#api-key

## ETF Data Strategy

1. **Holdings Priority**
   - **Financial Modeling Prep** (`stable/etf/holdings` → `api/v3/etf/holdings`)
   - **AlphaVantage** (`ETF_PROFILE`) if FMP is unavailable or rate-limited
   - **Yahoo Finance** (`funds_data.top_holdings`) as final fallback
   - Money-market and bond-style ETFs are excluded automatically using keyword heuristics

2. **Exposure Priority**
   - FMP country, sector, and asset allocation endpoints supply granular weights
   - Portfolio weights scale each ETF exposure to produce aggregate country/sector/asset-class views
   - Weight-only portfolios cache aggregated exposure CSVs using a hash signature to avoid redundant API calls

3. **Metadata Augmentation**
   - FMP overview endpoints provide issuer, focus, AUM, and expense ratio data when available
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

1. **API Rate Limits**: FMP free tiers vary by plan; AlphaVantage free tier allows 25 calls/day. Both clients rotate across available keys and log rate-limit notices—add multiple keys in `.env` when possible.

2. **Portfolio Updates**: Run `simple_portfolio_analysis.py` to get current snapshot. For daily tracking, schedule runs outside trading hours.

3. **Data Quality**: FMP generally provides the deepest ETF datasets (holdings, exposures). AlphaVantage bridges gaps. Yahoo Finance is a last resort and may omit many international funds.

4. **Configuration Management**: Use separate JSON files for different portfolios (`config_personal.json`, `config_retirement.json`, etc.).

## Troubleshooting

### "FMP API key not found"
- Ensure `.env` file exists in project root
- Verify `FMP_API_KEY` (and optional numbered variants) are defined without quotes
- Restart the session after editing `.env` so environment variables reload

### "AlphaVantage API key not found"
- Confirm fallback keys (`ALPHAVANTAGE_API_KEY`, `ALPHAVANTAGE_API_KEY_1`, …) are present
- Remove extraneous whitespace or quote characters

### "No holdings data for [ETF]"
- Some ETFs are premium-only on FMP; AlphaVantage will be tried next automatically
- European or synthetic ETFs may not be covered by either API—Yahoo Finance fallback will attempt a truncated snapshot
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
│   ├── alpha_vantage.py      # AlphaVantage API client
│   └── fmp.py                # Financial Modeling Prep API client
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

