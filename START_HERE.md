# START HERE - Capital Compass

## Welcome!

Your professional portfolio analysis toolkit is complete and ready to use. This document will get you started in 5 minutes.

## What Was Built

Capital Compass is a complete portfolio analysis and quantitative simulation toolkit with:

### Portfolio Analysis
- Real-time portfolio valuation
- Asset allocation visualization
- Sector exposure breakdown
- ETF look-through analysis

### Index Simulation
- S&P 500 counterfactual analysis
- "What if" scenarios (e.g., without Magnificent 7)
- Comprehensive performance metrics
- Risk-adjusted return calculations

### Analysis Tools
- Sharpe, Sortino, Calmar ratios
- Maximum drawdown analysis
- Alpha and beta calculations
- Rolling performance analysis

## Quick Start (3 Steps)

### Step 1: Setup Environment

```bash
cd ~/Desktop/NiklasProjects/CapitalCompass
conda activate capital_compass
```

If you haven't created the environment yet:
```bash
conda create -n capital_compass python=3.10
conda activate capital_compass
pip install -r requirements.txt
```

### Step 2: Configure Your Portfolio

Edit `src/config_ticker.json` with your holdings:

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

### Step 3: Run Analysis

**Option A - Command Line (Quick):**
```bash
cd src
python main.py
```

**Option B - Jupyter Notebooks (Recommended):**
```bash
jupyter notebook
```
Then open:
- `notebooks/00_Getting_Started.ipynb` (first time)
- `notebooks/01_Portfolio_Analysis.ipynb` (portfolio)
- `notebooks/02_Index_Simulation.ipynb` (index simulation)

## What You'll See

### Portfolio Analysis Output
1. Asset allocation donut chart (interactive)
2. Sector exposure breakdown
3. Holdings table with current values
4. Total portfolio value

### Index Simulation Output
1. Performance comparison chart (3 scenarios)
2. Comprehensive metrics table
3. Drawdown visualization
4. Rolling returns analysis

## Project Structure

```
CapitalCompass/
├── src/
│   ├── core/                    # Core analysis modules
│   │   ├── portfolio.py         # Portfolio analysis
│   │   ├── market_sim.py        # Index simulation
│   │   ├── etf_analyzer.py      # ETF analysis
│   │   └── performance_metrics.py # Performance calculations
│   ├── config_ticker.json       # YOUR PORTFOLIO (edit this!)
│   └── main.py                  # Run from command line
├── notebooks/
│   ├── 00_Getting_Started.ipynb      # Start here
│   ├── 01_Portfolio_Analysis.ipynb   # Detailed portfolio
│   └── 02_Index_Simulation.ipynb     # Index "what-if"
├── README.md                    # Full documentation
├── QUICKSTART.md               # Quick reference
└── requirements.txt            # Dependencies
```

## Documentation

- **START_HERE.md** - This file (you are here)
- **QUICKSTART.md** - Quick reference guide
- **README.md** - Complete documentation with methodology
- **PROJECT_STRUCTURE.md** - Detailed structure and architecture
- **IMPLEMENTATION_SUMMARY.md** - Technical implementation details

## Example Usage

### Analyze Your Portfolio
```python
from core.portfolio import analyze_portfolio_composition

fig_asset, fig_sector = analyze_portfolio_composition('config_ticker.json')
fig_asset.show()  # Opens in browser
```

### Simulate S&P 500
```python
from core.market_sim import analyze_index_exclusion

# What if S&P 500 without Magnificent 7?
magnificent_seven = ['AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'META', 'TSLA']

fig = analyze_index_exclusion(
    exclusion_list=magnificent_seven,
    start_date='2020-01-01'
)
fig.show()
```

### Calculate Performance Metrics
```python
from core.performance_metrics import generate_performance_report, print_performance_report
import yfinance as yf

# Download data
data = yf.download('SPY', start='2020-01-01')
returns = data['Adj Close'].pct_change().dropna()

# Generate comprehensive report
report = generate_performance_report(returns, risk_free_rate=0.02)
print_performance_report(report)
```

## Next Steps

1. **Test Installation:**
   - Open `notebooks/00_Getting_Started.ipynb`
   - Run all cells to verify everything works

2. **Analyze Your Portfolio:**
   - Edit `src/config_ticker.json` with your holdings
   - Run `notebooks/01_Portfolio_Analysis.ipynb`

3. **Explore Simulations:**
   - Open `notebooks/02_Index_Simulation.ipynb`
   - Try different exclusion lists
   - Experiment with date ranges

4. **Customize:**
   - Modify parameters in `src/config.py`
   - Add your own analysis in new notebooks
   - Extend core modules as needed

## Tips & Tricks

### Ticker Symbols
- Use Yahoo Finance format: "BRK-B" not "BRK.B"
- For Alphabet: "GOOG" or "GOOGL"
- Case matters: "AAPL" not "aapl"

### Portfolio Types
- `"type": "stock"` - Individual stocks
- `"type": "etf"` - Exchange-traded funds

### Performance
- First run downloads data (takes time)
- S&P 500 simulation: ~2-3 minutes
- Portfolio analysis: ~10-30 seconds

### Troubleshooting
- If imports fail: `pip install -r requirements.txt`
- If data fetch fails: check ticker symbols
- If plots don't show: check browser popup blocker

## Key Features

### Portfolio Analysis
✓ Real-time valuation via Yahoo Finance
✓ Interactive visualizations
✓ Asset and sector breakdown
✓ ETF look-through (best-effort)
✓ Professional formatting

### Index Simulation
✓ S&P 500 constituent scraping
✓ Equal-weighted simulation
✓ Counterfactual analysis
✓ Performance comparison
✓ Comprehensive metrics

### Performance Metrics
✓ Sharpe ratio (risk-adjusted return)
✓ Sortino ratio (downside risk)
✓ Maximum drawdown
✓ Alpha and beta
✓ Information ratio
✓ Rolling returns

### Notebooks
✓ Interactive analysis
✓ Step-by-step guidance
✓ Editable parameters
✓ Professional formatting

## Support Resources

**Getting Started:**
- Run `notebooks/00_Getting_Started.ipynb`
- Read `QUICKSTART.md`

**Understanding Methodology:**
- Read `README.md` (comprehensive)
- Check `PROJECT_STRUCTURE.md` (architecture)

**Technical Details:**
- Review `IMPLEMENTATION_SUMMARY.md`
- Read inline code comments
- Check docstrings in modules

## Common Questions

**Q: How accurate is the index simulation?**
A: Uses equal-weighting (not market-cap). Directionally accurate, standard academic approach.

**Q: Can I analyze international stocks?**
A: Yes, if available on Yahoo Finance. Use correct ticker format.

**Q: Can I add more holdings?**
A: Yes, just edit `config_ticker.json` and add more entries.

**Q: How often is data updated?**
A: Real-time (fetched when you run analysis).

**Q: Can I export charts?**
A: Yes, plotly charts have export options (PNG, SVG, etc.).

## Final Checklist

Before you start:
- [ ] Conda environment activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Portfolio configured (`src/config_ticker.json`)
- [ ] Documentation reviewed (at least this file)

Ready to go:
- [ ] Run `notebooks/00_Getting_Started.ipynb`
- [ ] Analyze your portfolio
- [ ] Try an index simulation

## Contact & Contribution

This is your personal toolkit. Customize and extend as needed.

For questions:
1. Check documentation files
2. Review code comments
3. Examine notebook examples

## License

For personal use. Market data subject to Yahoo Finance terms. Not financial advice.

---

**You're all set! Open `notebooks/00_Getting_Started.ipynb` to begin.**

Happy analyzing!

