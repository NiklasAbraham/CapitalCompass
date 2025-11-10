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
Represents Exchange-Traded Funds with look-through capability:
- Primary data source: **AlphaVantage API** for holdings
- Fallback data source: Yahoo Finance `funds_data`
- Automatically excludes money market and bond funds from holdings lookup
- Provides performance metrics (YTD return, expense ratio, etc.)

### 2. API Integrations

Located in `src/api/`:

#### AlphaVantage Client (`alpha_vantage.py`)
Provides access to AlphaVantage API:
- **ETF Profile**: `get_etf_profile()` returns detailed holdings data
- **Quote Data**: `get_quote()` for real-time prices
- **Company Overview**: `get_company_overview()` for fundamentals
- Configuration: API key stored in `.env` file (see `.env.example`)

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
- Performs ETF look-through with AlphaVantage
- Shows aggregated exposure (direct + indirect holdings)
- Prints ETF performance metrics

## Data Flow

```
1. Portfolio Config (JSON)
   ↓
2. Asset Objects Created (Stock/ETF)
   ↓
3. Market Data Fetched (Yahoo Finance)
   ↓
4. ETF Holdings Retrieved (AlphaVantage → Yahoo Finance fallback)
   ↓
5. Analysis & Visualization
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

Create a `.env` file in project root:

```bash
ALPHAVANTAGE_API_KEY=your_api_key_here
```

Get a free API key at: https://www.alphavantage.co/support/#api-key

## ETF Holdings Strategy

1. **AlphaVantage API (Primary)**
   - Comprehensive holdings data
   - Updated regularly
   - Free tier: 25 API calls/day
   - Best for US-listed ETFs

2. **Yahoo Finance (Fallback)**
   - Limited holdings data
   - Not available for all ETFs
   - No API key required
   - Works for many international ETFs

3. **Exclusions**
   - Money market funds
   - Government bond funds
   - Corporate bond term funds
   - Cash management ETFs
   
   These are identified by keywords in the ETF name and automatically excluded from holdings lookup.

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

1. **API Rate Limits**: AlphaVantage free tier allows 25 calls/day. The system falls back to Yahoo Finance automatically.

2. **Portfolio Updates**: Run `simple_portfolio_analysis.py` to get current snapshot. For daily tracking, schedule runs outside trading hours.

3. **Data Quality**: AlphaVantage provides better ETF holdings data than Yahoo Finance. Consider upgrading to premium for production use.

4. **Configuration Management**: Use separate JSON files for different portfolios (`config_personal.json`, `config_retirement.json`, etc.).

## Troubleshooting

### "AlphaVantage API key not found"
- Ensure `.env` file exists in project root
- Check that `ALPHAVANTAGE_API_KEY` is set correctly
- Verify no extra spaces or quotes around the key

### "No holdings data for [ETF]"
- Check if ETF is listed on US exchanges (AlphaVantage limitation)
- European ETFs may only work with Yahoo Finance fallback
- Money market/bond funds are intentionally excluded

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

