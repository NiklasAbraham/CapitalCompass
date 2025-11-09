"""
Core modules for Capital Compass toolkit.

This package contains the main analysis modules:
- portfolio: Portfolio composition analysis
- market_sim: Index simulation and constituent scraping
- etf_analyzer: ETF holdings analysis
- performance_metrics: Performance and risk calculations
"""

from .etf_analyzer import (
    analyze_portfolio_with_lookthrough,
    get_etf_holdings,
    get_etf_info,
)
from .market_sim import analyze_index_exclusion, get_sp500_tickers
from .performance_metrics import (
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    generate_performance_report,
    print_performance_report,
)
from .portfolio import analyze_portfolio_composition

__all__ = [
    "analyze_portfolio_composition",
    "get_sp500_tickers",
    "analyze_index_exclusion",
    "get_etf_holdings",
    "analyze_portfolio_with_lookthrough",
    "get_etf_info",
    "generate_performance_report",
    "print_performance_report",
    "calculate_sharpe_ratio",
    "calculate_sortino_ratio",
    "calculate_max_drawdown",
]
