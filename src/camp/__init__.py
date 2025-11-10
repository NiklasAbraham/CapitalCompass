"""
Analysis Package
================

Higher-level and experimental analysis modules live here.
Currently includes CAPM data preparation & optimisation helpers.
"""

from .capm_data import CapmDataset, compute_returns, fetch_price_data, prepare_capm_dataset
from .capm_optimizer import (
    CapmSummary,
    calculate_beta,
    capm_expected_returns,
    generate_capm_portfolio_summary,
    minimise_variance,
    optimise_max_sharpe,
    summarise_capm,
)

__all__ = [
    "CapmDataset",
    "CapmSummary",
    "calculate_beta",
    "capm_expected_returns",
    "compute_returns",
    "fetch_price_data",
    "generate_capm_portfolio_summary",
    "minimise_variance",
    "optimise_max_sharpe",
    "prepare_capm_dataset",
    "summarise_capm",
]

