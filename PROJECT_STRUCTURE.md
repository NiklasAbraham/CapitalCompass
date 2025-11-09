# Capital Compass - Project Structure

## Overview

Capital Compass is a professional portfolio analysis and quantitative simulation toolkit built with Python. This document outlines the complete project structure and module organization.

## Directory Structure

```
CapitalCompass/
│
├── src/                              # Source code directory
│   ├── core/                         # Core analysis modules
│   │   ├── __init__.py              # Package initialization
│   │   ├── portfolio.py             # Portfolio composition analysis
│   │   ├── market_sim.py            # Index simulation & S&P 500 scraping
│   │   ├── etf_analyzer.py          # ETF holdings analysis
│   │   └── performance_metrics.py   # Risk & return calculations
│   │
│   ├── config.py                     # Configuration parameters
│   ├── config_ticker.json            # Portfolio holdings definition
│   └── main.py                       # Main execution script
│
├── notebooks/                        # Jupyter notebooks for analysis
│   ├── 00_Getting_Started.ipynb     # Installation verification & quick start
│   ├── 01_Portfolio_Analysis.ipynb  # Detailed portfolio analysis
│   └── 02_Index_Simulation.ipynb    # Index counterfactual simulation
│
├── requirements.txt                  # Python package dependencies
├── README.md                         # Main documentation
├── QUICKSTART.md                     # Quick start guide
├── PROJECT_STRUCTURE.md              # This file
└── .gitignore                        # Git ignore rules
```

## Module Descriptions

### Core Modules (`src/core/`)

#### 1. `portfolio.py`
**Purpose:** Portfolio composition and allocation analysis

**Key Functions:**
- `analyze_portfolio_composition()` - Main analysis function
  - Loads portfolio from JSON
  - Fetches real-time market data
  - Calculates weights and allocations
  - Generates interactive visualizations

**Outputs:**
- Asset allocation pie chart
- Sector allocation pie chart
- Portfolio statistics

#### 2. `market_sim.py`
**Purpose:** S&P 500 simulation and counterfactual analysis

**Key Functions:**
- `get_sp500_tickers()` - Scrapes S&P 500 constituents from Wikipedia
- `analyze_index_exclusion()` - Performs counterfactual simulation
  - Downloads historical data
  - Calculates equal-weighted returns
  - Compares baseline vs. modified portfolios
  - Generates performance comparison plots

**Outputs:**
- Cumulative performance chart (3 scenarios)
- Comparison statistics

#### 3. `etf_analyzer.py`
**Purpose:** ETF holdings analysis and look-through

**Key Functions:**
- `get_etf_holdings()` - Retrieves ETF holdings (best-effort)
- `analyze_portfolio_with_lookthrough()` - Aggregates direct + indirect exposure
- `get_etf_info()` - Fetches comprehensive ETF information

**Outputs:**
- Combined exposure DataFrame
- ETF metadata

**Note:** ETF holdings data availability is limited with free APIs.

#### 4. `performance_metrics.py`
**Purpose:** Quantitative performance and risk analysis

**Key Functions:**

**Return Metrics:**
- `calculate_annualized_return()` - Geometric mean return
- `calculate_cumulative_returns()` - Cumulative performance

**Risk Metrics:**
- `calculate_volatility()` - Annualized standard deviation
- `calculate_max_drawdown()` - Peak-to-trough decline

**Risk-Adjusted Metrics:**
- `calculate_sharpe_ratio()` - Return per unit of total risk
- `calculate_sortino_ratio()` - Return per unit of downside risk
- `calculate_calmar_ratio()` - Return per unit of max drawdown

**Benchmark-Relative Metrics:**
- `calculate_beta()` - Market sensitivity
- `calculate_alpha()` - Jensen's alpha (excess return)
- `calculate_information_ratio()` - Return per unit of tracking error

**Comprehensive Analysis:**
- `generate_performance_report()` - All metrics in one report
- `print_performance_report()` - Formatted console output

### Configuration (`src/config.py`)

Centralized configuration parameters:

```python
PORTFOLIO_FILE = "config_ticker.json"
SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S&P_500_companies"
DEFAULT_RISK_FREE_RATE = 0.02  # 2% annual
TRADING_DAYS_PER_YEAR = 252
DEFAULT_START_DATE = "2020-01-01"
```

### Portfolio Configuration (`src/config_ticker.json`)

JSON file defining portfolio holdings:

```json
[
    {
        "ticker": "AAPL",      // Ticker symbol (Yahoo Finance format)
        "units": 10,           // Number of shares/units
        "type": "stock"        // "stock" or "etf"
    }
]
```

### Main Script (`src/main.py`)

Command-line interface for running analyses:

**Functions:**
- `run_portfolio_analysis()` - Executes portfolio analysis
- `run_simulation_analysis()` - Executes index simulation
- `main()` - Orchestrates full workflow

**Usage:**
```bash
cd src
python main.py
```

## Jupyter Notebooks (`notebooks/`)

### 1. `00_Getting_Started.ipynb`
**Purpose:** Installation verification and quick test

**Contents:**
- Import verification
- Data fetching test
- Quick portfolio analysis
- S&P 500 constituent test

### 2. `01_Portfolio_Analysis.ipynb`
**Purpose:** Comprehensive portfolio analysis

**Sections:**
1. Load portfolio configuration
2. Asset allocation visualization
3. Detailed holdings table
4. ETF look-through analysis
5. ETF details and information
6. Sector breakdown

### 3. `02_Index_Simulation.ipynb`
**Purpose:** Quantitative index simulation

**Sections:**
1. Configuration (exclusion list, dates)
2. Fetch S&P 500 constituents
3. Run counterfactual simulation
4. Detailed performance metrics
5. Comparative analysis table
6. Drawdown analysis
7. Rolling performance visualization

## Data Flow

### Portfolio Analysis Flow
```
config_ticker.json
    ↓
portfolio.py → yfinance API → Market Data
    ↓
Calculations (weights, allocations)
    ↓
plotly → Interactive Visualizations
```

### Index Simulation Flow
```
Wikipedia (S&P 500 list)
    ↓
market_sim.py → yfinance API → Historical Data
    ↓
Calculate Returns (equal-weighted)
    ↓
Baseline vs. Modified Comparison
    ↓
performance_metrics.py → Risk/Return Stats
    ↓
plotly → Performance Charts
```

## Dependencies

### Core Libraries
- **pandas** (≥2.0.0) - Data manipulation
- **yfinance** (≥0.2.28) - Market data API
- **plotly** (≥5.14.0) - Interactive visualizations
- **numpy** (≥1.24.0) - Numerical computations

### Web Scraping
- **beautifulsoup4** (≥4.12.0) - HTML parsing
- **lxml** (≥4.9.0) - XML/HTML parser
- **requests** (≥2.31.0) - HTTP requests

### Notebooks
- **jupyter** (≥1.0.0) - Jupyter environment
- **notebook** (≥6.5.0) - Notebook server
- **ipykernel** (≥6.23.0) - Jupyter kernel

### Additional
- **scipy** (≥1.10.0) - Scientific computing

## Usage Patterns

### Command Line Usage

```bash
# Activate environment
conda activate capital_compass

# Run full analysis
cd src
python main.py
```

### Programmatic Usage

```python
# Portfolio analysis
from core.portfolio import analyze_portfolio_composition

fig_asset, fig_sector = analyze_portfolio_composition('config_ticker.json')
fig_asset.show()

# Index simulation
from core.market_sim import analyze_index_exclusion

fig = analyze_index_exclusion(
    exclusion_list=['AAPL', 'MSFT', 'NVDA'],
    start_date='2020-01-01'
)
fig.show()

# Performance metrics
from core.performance_metrics import generate_performance_report
import yfinance as yf

data = yf.download('SPY', start='2020-01-01')
returns = data['Adj Close'].pct_change().dropna()
report = generate_performance_report(returns)
```

### Interactive Analysis

```bash
# Start Jupyter
jupyter notebook

# Open notebooks:
# - 00_Getting_Started.ipynb (first time)
# - 01_Portfolio_Analysis.ipynb (portfolio)
# - 02_Index_Simulation.ipynb (index simulation)
```

## Extension Points

The modular design allows for easy extensions:

1. **Add New Asset Classes**
   - Extend `portfolio.py` with new asset type handlers
   - Add corresponding analysis functions

2. **Add New Performance Metrics**
   - Implement new functions in `performance_metrics.py`
   - Update `generate_performance_report()`

3. **Add New Visualizations**
   - Create new plotting functions using plotly
   - Integrate into notebooks or main.py

4. **Add New Data Sources**
   - Implement new data fetching modules
   - Update existing modules to use new sources

5. **Add Portfolio Optimization**
   - Create new module `portfolio_optimizer.py`
   - Implement mean-variance optimization
   - Add to notebooks

6. **Add Backtesting Engine**
   - Create new module `backtest.py`
   - Implement rebalancing strategies
   - Add performance attribution

## Best Practices

### Configuration
- Keep sensitive data out of version control
- Use `config.py` for constants
- Use JSON files for data

### Code Organization
- One module per major functionality
- Clear function documentation
- Type hints where appropriate

### Error Handling
- Try-except blocks for API calls
- Informative error messages
- Graceful degradation

### Performance
- Cache S&P 500 constituent list
- Use vectorized operations (pandas/numpy)
- Progress indicators for long operations

## Troubleshooting

### Common Issues

**Import Errors:**
- Ensure conda environment is activated
- Reinstall: `pip install -r requirements.txt`

**Data Fetching Errors:**
- Check internet connection
- Verify ticker symbols (Yahoo Finance format)
- Some tickers may have limited data

**Slow Performance:**
- Downloading 500+ tickers takes time
- Consider reducing date range
- Cache downloaded data

### Debugging

Enable detailed error messages in main.py:
```python
import traceback
traceback.print_exc()
```

## License and Disclaimer

For educational and personal use. Market data subject to Yahoo Finance terms of service. Not financial advice.

## Support

- Review README.md for methodology
- Check QUICKSTART.md for common tasks
- Examine notebook examples
- Read inline code comments

---

**Last Updated:** November 2025
**Version:** 1.0
**Python Version:** 3.10+

