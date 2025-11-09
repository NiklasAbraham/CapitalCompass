# Capital Compass - Quick Start Guide

This guide will get you up and running with Capital Compass in under 5 minutes.

## Installation

1. **Activate your conda environment:**

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

## Configuration

2. **Edit your portfolio:**

Open `src/config_ticker.json` and define your holdings:

```json
[
    {
        "ticker": "AAPL",
        "units": 10,
        "type": "stock"
    },
    {
        "ticker": "NVDA",
        "units": 5,
        "type": "stock"
    },
    {
        "ticker": "VOO",
        "units": 50,
        "type": "etf"
    }
]
```

## Running Analysis

### Option 1: Command Line (Quick)

```bash
cd src
python main.py
```

This will:
- Load your portfolio
- Generate interactive visualizations (opens in browser)
- Run S&P 500 simulation analysis

### Option 2: Jupyter Notebooks (Recommended)

```bash
jupyter notebook
```

Then open:
- `notebooks/01_Portfolio_Analysis.ipynb` - Detailed portfolio breakdown
- `notebooks/02_Index_Simulation.ipynb` - Index counterfactual analysis

## What You'll See

### Portfolio Analysis
- Asset allocation pie chart
- Sector exposure breakdown
- Holdings table with current values
- ETF look-through (when available)

### Index Simulation
- S&P 500 performance comparison
- "What if" scenario (e.g., without Magnificent 7)
- Performance metrics (Sharpe ratio, max drawdown, etc.)
- Rolling returns analysis

## Customization

### Change Simulation Parameters

Edit `notebooks/02_Index_Simulation.ipynb`:

```python
# Try different exclusion lists
exclusion_list = ['AAPL', 'MSFT', 'GOOGL']

# Try different time periods
start_date = '2015-01-01'
```

### Add More Holdings

Simply edit `src/config_ticker.json`:

```json
[
    {
        "ticker": "TSLA",
        "units": 20,
        "type": "stock"
    }
]
```

Supported types: `"stock"` or `"etf"`

## Troubleshooting

**"ModuleNotFoundError"**
- Make sure conda environment is activated: `conda activate capital_compass`
- Reinstall dependencies: `pip install -r requirements.txt`

**"FileNotFoundError: config_ticker.json"**
- Make sure you're running from the `src/` directory
- Or use absolute paths

**"No data found for ticker"**
- Check that ticker symbol is correct (use Yahoo Finance format)
- Some tickers may not have data for the requested date range

## Next Steps

1. Read the full README.md for detailed methodology
2. Explore the Jupyter notebooks for interactive analysis
3. Experiment with different portfolios and exclusion lists
4. Review performance metrics to understand risk/return characteristics

## Tips

- Use uppercase for ticker symbols (e.g., "AAPL" not "aapl")
- For Alphabet, use "GOOG" or "GOOGL" (both classes)
- For Berkshire Hathaway, use "BRK-B" (Yahoo Finance format)
- ETF look-through data may be limited with free APIs

## Support

For issues or questions, refer to:
- README.md for full documentation
- Code comments in src/core/ modules
- Jupyter notebooks for usage examples

Happy analyzing!

