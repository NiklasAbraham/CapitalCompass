# Capital Compass

**A Professional Portfolio Analysis and Quantitative Simulation Toolkit**

Capital Compass is a Python-based toolkit for analyzing personal investment portfolios and conducting counterfactual simulations on market indices. The toolkit combines modern data visualization with rigorous quantitative analysis to provide deep insights into portfolio composition and market dynamics.

## Features

### 1. Portfolio Composition Analysis
- Real-time portfolio valuation using live market data
- Asset allocation visualization with interactive charts
- Sector exposure analysis
- ETF look-through analysis (best-effort based on data availability)
- Comprehensive holdings breakdown

### 2. Index Simulation & Counterfactual Analysis
- S&P 500 constituent scraping from Wikipedia
- Equal-weighted index simulation
- Counterfactual "what-if" analysis (e.g., "S&P 500 without the Magnificent 7")
- Comparative performance analysis

### 3. Performance Metrics
- Total and annualized returns
- Risk metrics (volatility, maximum drawdown)
- Risk-adjusted ratios (Sharpe, Sortino, Calmar)
- Benchmark-relative metrics (alpha, beta, information ratio)
- Rolling performance analysis
- Drawdown visualization

## Project Structure

```
CapitalCompass/
├── src/
│   ├── core/
│   │   ├── portfolio.py           # Portfolio composition analysis
│   │   ├── market_sim.py          # Index simulation and scraping
│   │   ├── etf_analyzer.py        # ETF holdings analysis
│   │   └── performance_metrics.py # Risk and return calculations
│   ├── config.py                   # Configuration parameters
│   ├── config_ticker.json          # Portfolio holdings definition
│   └── main.py                     # Main execution script
├── notebooks/
│   ├── 01_Portfolio_Analysis.ipynb # Interactive portfolio analysis
│   └── 02_Index_Simulation.ipynb   # Interactive index simulation
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

## Installation

### Prerequisites
- Python 3.8 or higher
- Conda (recommended) or pip

### Setup with Conda

1. Clone the repository:
```bash
cd ~/Desktop/NiklasProjects/CapitalCompass
```

2. Create a conda environment:
```bash
conda create -n capital_compass python=3.10
conda activate capital_compass
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Configuration

Edit `src/config_ticker.json` to define your portfolio:

```json
[
    {
        "ticker": "AAPL",
        "units": 10,
        "type": "stock"
    },
    {
        "ticker": "VOO",
        "units": 50,
        "type": "etf"
    }
]
```

### Running Analysis

#### Option 1: Command Line

```bash
conda activate capital_compass
cd src
python main.py
```

This will:
1. Load your portfolio from `config_ticker.json`
2. Generate asset and sector allocation visualizations
3. Run the index simulation analysis
4. Open interactive plots in your browser

#### Option 2: Jupyter Notebooks (Recommended)

```bash
conda activate capital_compass
jupyter notebook
```

Navigate to the `notebooks/` directory and open:

**01_Portfolio_Analysis.ipynb**
- Comprehensive portfolio composition analysis
- ETF look-through
- Sector breakdown
- Holdings tables

**02_Index_Simulation.ipynb**
- S&P 500 counterfactual simulation
- Performance metrics comparison
- Drawdown analysis
- Rolling returns visualization

## Methodology

### Portfolio Analysis

The toolkit fetches real-time market data using the `yfinance` library, which accesses Yahoo Finance's API. For each holding:

1. Current price is retrieved
2. Market value is calculated (units × price)
3. Portfolio weights are computed
4. Sector data is aggregated

**ETF Look-Through:** The toolkit attempts to retrieve ETF holdings to show indirect exposure. However, this data is often incomplete or unavailable through free APIs. Direct holdings are always accurately represented.

### Index Simulation

The S&P 500 is a market-capitalization-weighted index. Truly accurate counterfactual simulation would require historical daily market-cap data for all 500 constituents, which is not freely available.

**Solution:** This toolkit uses an **equal-weighted index proxy**, a standard academic approach. The methodology:

1. Scrape current S&P 500 constituents from Wikipedia
2. Download historical adjusted close prices for all constituents
3. Calculate daily returns for each stock
4. Create equal-weighted portfolios:
   - **Baseline:** Mean return of all 500 stocks
   - **Modified:** Mean return excluding specified stocks
5. Compare against the official S&P 500 index (^GSPC)

This approach is directionally accurate and widely used in quantitative research for analyzing constituent contribution.

## Performance Metrics

### Return Metrics
- **Total Return:** Cumulative return over the period
- **Annualized Return:** Geometric mean return, annualized

### Risk Metrics
- **Volatility:** Annualized standard deviation of returns
- **Maximum Drawdown:** Largest peak-to-trough decline

### Risk-Adjusted Metrics
- **Sharpe Ratio:** Excess return per unit of total risk
- **Sortino Ratio:** Excess return per unit of downside risk
- **Calmar Ratio:** Annualized return divided by maximum drawdown

### Benchmark-Relative Metrics
- **Beta:** Sensitivity to benchmark movements
- **Alpha:** Excess return over expected return (Jensen's alpha)
- **Information Ratio:** Excess return per unit of tracking error

## Data Sources

- **Market Data:** Yahoo Finance via `yfinance`
- **S&P 500 Constituents:** Wikipedia (List of S&P 500 companies)

## Limitations and Considerations

1. **Data Quality:** Free market data may have delays, gaps, or inaccuracies
2. **ETF Holdings:** Look-through data is best-effort and may be incomplete
3. **Equal Weighting:** Index simulation uses equal weighting, not market-cap weighting
4. **Survivorship Bias:** Uses current constituents, not historical composition
5. **No Rebalancing:** Does not account for index rebalancing events
6. **No Dividends:** Uses adjusted close prices (dividends reinvested)

## Technical Stack

- **Python 3.10**
- **pandas:** Data manipulation and time-series analysis
- **yfinance:** Yahoo Finance API wrapper
- **plotly:** Interactive visualizations
- **beautifulsoup4 / lxml:** Web scraping for S&P 500 constituents
- **numpy / scipy:** Numerical computations
- **jupyter:** Interactive analysis notebooks

## Examples

### Analyzing Your Portfolio

```python
from core.portfolio import analyze_portfolio_composition

fig_asset, fig_sector = analyze_portfolio_composition('config_ticker.json')
fig_asset.show()
fig_sector.show()
```

### Simulating Index Performance

```python
from core.market_sim import analyze_index_exclusion

magnificent_seven = ['AAPL', 'MSFT', 'GOOG', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA']
fig = analyze_index_exclusion(
    exclusion_list=magnificent_seven,
    start_date='2020-01-01'
)
fig.show()
```

### Generating Performance Reports

```python
from core.performance_metrics import generate_performance_report, print_performance_report
import yfinance as yf

# Download data
data = yf.download('SPY', start='2020-01-01')
returns = data['Adj Close'].pct_change().dropna()

# Generate report
report = generate_performance_report(returns, risk_free_rate=0.02)
print_performance_report(report)
```

## Further Development

Potential enhancements for this toolkit:

1. **Market-Cap Weighted Simulation:** Integrate with paid data providers for accurate historical market caps
2. **Portfolio Optimization:** Add mean-variance optimization capabilities
3. **Monte Carlo Simulation:** Implement forward-looking scenario analysis
4. **Backtesting Engine:** Add support for rebalancing strategies
5. **Additional Asset Classes:** Extend beyond equities (bonds, commodities, crypto)
6. **Risk Models:** Implement factor models (Fama-French, etc.)
7. **Tax Analysis:** Add tax-loss harvesting and capital gains tracking

## References and Further Reading

### Books
- **"Python for Finance: Mastering Data-Driven Finance" (2nd Ed.)** by Yves Hilpisch
  - Comprehensive guide to quantitative finance with Python
  - Covers everything from time-series analysis to ML in trading

### Online Resources
- **QuantStart** (quantstart.com): Articles on backtesting and algorithmic trading
- **Portfolio Visualizer** (portfoliovisualizer.com): Reference for portfolio analytics
- **Yahoo Finance API** (yfinance documentation): Data source documentation

### Academic Papers
- Sharpe, William F. (1994). "The Sharpe Ratio"
- Sortino, Frank A. (1994). "Downside Risk"
- Jensen, Michael C. (1968). "The Performance of Mutual Funds"

## License

This project is for educational and personal use. Market data is provided by Yahoo Finance and subject to their terms of service.

## Contributing

This is a personal project, but suggestions and improvements are welcome. Please ensure all code follows the existing style and includes appropriate documentation.

## Contact

For questions or suggestions, please create an issue in the repository.

---

**Disclaimer:** This toolkit is for informational and educational purposes only. It does not constitute financial advice. Always conduct your own research and consult with qualified financial professionals before making investment decisions.

