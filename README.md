# Capital Compass

A Python-based toolkit for portfolio composition analysis and S&P 500 “what-if” simulations. It uses `pandas`, `yfinance`, and `matplotlib` to fetch live market data, generate publication-ready PNG charts, and quantify risk/return trade-offs.

## NEW: Asset-Based Architecture with FMP & AlphaVantage

CapitalCompass now features a flexible **class-based architecture** with integrated **Financial Modeling Prep (FMP)** and **AlphaVantage API** support:
- Asset Classes (`Stock`, `ETF`) with polymorphic behavior
- ETF look-through using FMP API (primary), AlphaVantage API (fallback), and Yahoo Finance (final fallback)
- ETF country/sector/asset breakdowns via FMP secondary endpoints
- Automatic API key rotation when rate limits are hit
- Smart exclusions for money market and bond funds
- Extensible design for adding new asset types

See [ARCHITECTURE.md](ARCHITECTURE.md) for complete technical documentation.

## Quick Start

```bash
cd ~/Desktop/NiklasProjects/CapitalCompass
conda create -n capital_compass python=3.10    # first time only
conda activate capital_compass
pip install -r requirements.txt
```

Optional first-run check:

```bash
jupyter notebook notebooks/00_Getting_Started.ipynb
```

This notebook verifies imports, fetches a price sample, inspects your portfolio config, and runs a mini analysis.

## Configure Your Portfolio

Holdings live in `src/config_ticker.json` (rename to `portfolio.json` if you like).
You can specify positions either by absolute units *or* by percentage weights:

```json
[
  {"ticker": "AAPL", "units": 10,  "type": "stock"},
  {"ticker": "NVDA", "units": 5,   "type": "stock"},
  {"ticker": "VOO",  "units": 50,  "type": "etf"}
]
```

```json
[
  {"ticker": "CSPX.L", "weight": 0.36, "type": "etf"},
  {"ticker": "IUSM.L", "weight": 0.06, "type": "etf"},
  {"ticker": "XCS6.L", "weight": 0.04, "type": "etf"}
]
```

- Weight values may be fractions (summing to 1) or percentages (summing to 100).  
- Mixing units and weights in the same file is not supported.
- Tickers must use Yahoo Finance symbols (e.g., `BRK-B`, `BF-B`, `GOOG`, `GOOGL`).

## Run the Toolkit

### New: Asset-Based Analysis (Recommended)

Run the enhanced portfolio analysis with AlphaVantage integration:

```bash
cd ~/Desktop/NiklasProjects/CapitalCompass
conda activate capital
python src/analysis/simple_portfolio_analysis.py
```

This provides:
- Current portfolio distribution with asset allocation charts
- ETF look-through using FMP API (primary), AlphaVantage API (fallback), and Yahoo Finance (final fallback)
- Aggregated exposure showing direct and indirect holdings
- ETF-level country / sector / asset-class allocation summaries (saved as CSVs)
- Performance metrics for each ETF

**Setup API Keys** (optional but highly recommended):

Create a `.env` file in the project root with your API keys:

```bash
# Financial Modeling Prep (FMP) - tried first
FMP_API_KEY=your_fmp_key_here

# AlphaVantage - tried if FMP doesn't have data
ALPHAVANTAGE_API_KEY=your_alphavantage_key_here
```

Where to get free API keys:
- **FMP**: https://site.financialmodelingprep.com/ (recommended, better ETF coverage)
- **AlphaVantage**: https://www.alphavantage.co/support/#api-key

**Multiple API Keys for Rotation** (recommended):

Both clients support automatic key rotation when rate limits are hit. Add multiple keys like this:

```bash
# FMP keys
FMP_API_KEY=first_key
FMP_API_KEY_1=second_key
FMP_API_KEY_2=third_key

# AlphaVantage keys
ALPHAVANTAGE_API_KEY=first_key
ALPHAVANTAGE_API_KEY_1=second_key
ALPHAVANTAGE_API_KEY_2=third_key
```

The system will automatically cycle through keys when one hits a rate limit.

### Legacy Command Line

```bash
conda activate capital_compass
cd src
python main.py
```

The CLI loads your portfolio, saves asset/sector allocation charts under `outputs/`, and runs the default S&P 500 exclusion scenario (Magnificent Seven, 2020‑01‑01 onwards) with the resulting curve stored in the same folder.

### Jupyter Workbooks

- `notebooks/01_Portfolio_Analysis.ipynb` – deep dive into portfolio valuation, allocation, ETF look-through, and sector exposure.
- `notebooks/02_Index_Simulation.ipynb` – scrape constituents, compare equal-weight baseline vs. custom exclusions, compute performance statistics, drawdowns, and rolling returns.

Each cell is documented so you can tweak parameters (e.g., exclusion lists, start dates) on the fly.

## Features Overview

- **Portfolio Composition Analysis**
  - Live pricing via Yahoo Finance
  - Market value and weight calculation
  - Asset and sector allocation PNG charts (matplotlib pies)
  - ETF holdings look-through via FMP API (primary), AlphaVantage API (fallback), and Yahoo Finance (final fallback)
  - Automatic API key rotation for rate limit management
  - Intelligent caching to reduce redundant API calls
  - Portfolio-level ETF exposures: country, sector, and asset-class weights (with cached CSV outputs)
## FMP Endpoint Coverage

The toolkit integrates multiple FMP endpoints with graceful fallbacks:

- **Holdings**: `stable/etf/holdings` → fallback `api/v3/etf/holdings`
- **Country Allocation**: `stable/etf/country-weightings` → fallback `api/v3/etf-country-weightings`
- **Sector Allocation**: `stable/etf/sector-weightings` → fallback `api/v3/etf-sector-weightings`
- **Asset Allocation**: `stable/etf/asset-allocation` → fallback `api/v3/etf-asset-allocation`
- **ETF Overview / Metadata**: `stable/etf/information`, `stable/etf/profile` → fallback `api/v3/etf-profile`
- **Quotes / Profiles (Equities)**: `stable/quote`, `stable/profile`

Each request is logged with the endpoint and key index used. When rate limits or “Information” notices appear, keys rotate automatically. Successful responses are cached per-portfolio (hash-based) to minimise repeated API usage.

Generated CSV snapshots (saved under `outputs/`) include:
- `portfolio_country_exposure.csv`
- `portfolio_country_exposure_detail.csv`
- `portfolio_sector_exposure.csv`
- `portfolio_sector_exposure_detail.csv`
- `portfolio_asset_class_exposure.csv`
- `portfolio_asset_class_exposure_detail.csv`
- **CAPM Toolkit**
  - Fetch aligned asset/benchmark return series (`analysis.capm_data`)
  - Estimate betas and CAPM expected returns
  - Build maximum Sharpe and minimum variance portfolios with optional shorting
- **Index “What-If” Simulation**
  - Scrape S&P 500 symbols from Wikipedia (`pandas.read_html`)
  - Download historical adjusted closes for all constituents plus `^GSPC`
  - Build baseline/exclusion portfolios using **current market-cap weights** (falls back to equal weights if caps are missing)
  - Save cumulative performance comparison as a PNG line chart
- **Performance & Risk Metrics**
  - Total/annualised return, volatility, Sharpe, Sortino, Calmar
  - Beta, Jensen’s alpha, information ratio
  - Maximum drawdown with dates, rolling 1-year returns
  - Printable performance reports for quick review

## Architecture

```
CapitalCompass/
├── src/
│   ├── core/
│   │   ├── assets/
│   │   │   ├── base.py             # Asset base class
│   │   │   ├── stock.py            # Stock asset class
│   │   │   └── etf.py              # ETF asset class with API integration
│   │   ├── portfolio.py            # analyze_portfolio_composition
│   │   ├── market_sim.py           # get_sp500_tickers, analyze_index_exclusion
│   │   └── performance_metrics.py  # return/risk calculations
│   ├── api/
│   │   ├── fmp.py                  # Financial Modeling Prep client
│   │   └── alpha_vantage.py        # AlphaVantage client
│   ├── analysis/
│   │   └── simple_portfolio_analysis.py  # Standalone analysis script
│   ├── config.py                   # constants (file paths, defaults)
│   ├── config_ticker.json          # portfolio definition
│   └── main.py                     # CLI orchestrator
├── notebooks/                      # interactive workflows
└── outputs/                        # generated charts and cached data
```

Everything in `src/core` and `src/api` is importable so you can script custom workflows.

### CAPM Modules (Experimental)

Located under `src/analysis/`:

- `capm_data.py` – helpers to pull price history, compute returns, and package CAPM inputs in a `CapmDataset`.
- `capm_optimizer.py` – CAPM beta/expected-return estimation plus optimisation routines:
  - `summarise_capm` / `generate_capm_portfolio_summary`
  - `optimise_max_sharpe` for the tangency portfolio
  - `minimise_variance` for constrained minimum variance allocations

Example usage:

```python
from analysis import prepare_capm_dataset, generate_capm_portfolio_summary

dataset = prepare_capm_dataset(
    asset_tickers=["AAPL", "MSFT", "VOO"],
    benchmark_ticker="^GSPC",
    start_date="2018-01-01",
)

summary = generate_capm_portfolio_summary(dataset, allow_short=False)
print(summary["betas"])
print(summary["max_sharpe_weights"])
```

## Methodology Highlights

- **Portfolio valuation** uses `Ticker.fast_info['lastPrice']` and `Ticker.info['sector']`. ETFs are labeled `ETF / Other` when sector data is missing.
- **ETF look-through** uses a three-tier fallback system:
  1. **FMP API** (Financial Modeling Prep) is tried first for comprehensive holdings data
  2. **AlphaVantage API** is tried if FMP doesn't have data or hits rate limits
  3. **Yahoo Finance** is the final fallback using `yfinance` when API data is unavailable
  4. When all sources fail, ETFs are treated as single assets
  5. API responses are cached to reduce redundant calls for the same portfolio
- **ETF exposure aggregation**: FMP country/sector/asset allocation endpoints are scaled by portfolio weights to produce allocation snapshots, cached per portfolio (weight-based configs) and exported to CSV in `outputs/`.
- **API key rotation**: When rate limits are detected (via `Information` or `Note` fields), the system automatically rotates to the next available API key
- **Index simulation** default baseline uses today's market-cap weights fetched from Yahoo Finance. Historical point-in-time weights are not available for free, so this is a snapshot approximation; when market caps cannot be retrieved the code falls back to equal weighting. Symbols containing dots are converted to Yahoo's dash notation (e.g., `BRK.B → BRK-B`).

## Metrics Reference

- **Return**: cumulative, annualised.
- **Risk**: annualised volatility, maximum drawdown, drawdown curve.
- **Risk-adjusted**: Sharpe, Sortino, Calmar.
- **Benchmark-relative**: beta, Jensen’s alpha, information ratio (tracking error).
- **Rolling analysis**: 252-day rolling returns to see regime shifts.

Use `generate_performance_report` and `print_performance_report` for a ready-made summary.

## Limitations & Assumptions

1. Data comes from Yahoo Finance; outages or delays can occur.
2. ETF holdings data quality depends on API availability:
   - Free API tiers have daily rate limits (FMP: varies by plan, AlphaVantage: 25/day)
   - Some ETFs may not be covered by any API
   - Holdings data may be delayed or incomplete
3. Equal-weight simulations ignore market-cap differences and survivorship bias (current constituents only).
4. No automated rebalancing, tax modelling, or transaction cost estimation.
5. Dividends are implicitly handled via adjusted close, assuming reinvestment.

## Troubleshooting & Tips

- **Import errors** → double-check `conda activate capital` and reinstall requirements.
- **Ticker not found** → confirm Yahoo Finance symbol (case-sensitive, use dashes instead of dots).
- **API rate limits** → the system automatically rotates keys; add multiple keys in `.env` to increase throughput. Check console output for detailed API call logs.
- **No ETF holdings data** → verify your FMP/AlphaVantage keys are correct in `.env`. The system will fall back through all three data sources (FMP → AlphaVantage → Yahoo Finance).
- **Slow downloads** → fetching ~500 tickers can take minutes; narrow the exclusion list or date range while testing.
- **Missing charts** → check the `outputs/` directory for generated PNG files; rerun if downloads failed mid-way.

## Extending the Toolkit

Future enhancements could include:
- Market-cap weighted simulations (requires paid constituent weights)
- Portfolio optimisation (mean-variance, risk-parity)
- Monte Carlo forecasting and stress testing
- Event-driven backtesting with scheduled rebalances
- Multi-asset support (fixed income, commodities, crypto)
- Factor attribution (e.g., Fama-French variables)
- Tax-aware performance tracking

## License & Disclaimer

Capital Compass is provided for personal and educational use. Market data is sourced via `yfinance` and subject to Yahoo Finance terms. This toolkit does not constitute financial advice—consult a qualified professional before making investment decisions.

