"""
CAPM Optimisation Utilities
===========================

Tools to compute CAPM statistics (beta, expected return) and to
build mean-variance optimal portfolios that rely on the CAPM
expected return estimates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from analysis.capm_data import CapmDataset


@dataclass
class CapmSummary:
    """
    Stores the key CAPM statistics for a universe of assets.

    Attributes:
        betas: Series of asset betas relative to the benchmark.
        expected_returns: Series of CAPM expected returns.
        market_premium: Expected market excess return (E[R_m] - R_f).
    """

    betas: pd.Series
    expected_returns: pd.Series
    market_premium: float


def calculate_beta(
    asset_returns: pd.DataFrame, benchmark_returns: pd.Series
) -> pd.Series:
    """
    Compute regression betas using covariance / variance.

    Args:
        asset_returns: DataFrame where each column is an asset return series.
        benchmark_returns: Series of benchmark returns aligned with asset_returns.

    Returns:
        Pandas Series of betas indexed by asset symbol.
    """

    cov = asset_returns.covwith(benchmark_returns)
    benchmark_var = benchmark_returns.var()
    if np.isclose(benchmark_var, 0):
        raise ValueError("Benchmark variance is zero; cannot compute beta.")
    return cov / benchmark_var


def capm_expected_returns(
    betas: pd.Series, market_excess_return: float, risk_free_rate: float
) -> pd.Series:
    """
    Compute CAPM expected returns: E[R_i] = R_f + beta_i * (E[R_m] - R_f).

    Args:
        betas: Series of asset betas.
        market_excess_return: Expected market return minus risk-free rate.
        risk_free_rate: Annual risk-free rate.

    Returns:
        Series of CAPM expected returns.
    """

    return risk_free_rate + betas * market_excess_return


def summarise_capm(dataset: CapmDataset) -> CapmSummary:
    """
    Convenience wrapper that calculates betas and CAPM expected returns.

    Args:
        dataset: CapmDataset with aligned returns and risk-free rate.

    Returns:
        CapmSummary containing betas, expected returns, and market premium.
    """

    asset_returns = dataset.asset_returns
    benchmark_returns = dataset.benchmark_returns

    betas = calculate_beta(asset_returns, benchmark_returns)
    market_excess = benchmark_returns.mean() * 252 - dataset.risk_free_rate
    expected = capm_expected_returns(
        betas=betas,
        market_excess_return=market_excess,
        risk_free_rate=dataset.risk_free_rate,
    )

    return CapmSummary(betas=betas, expected_returns=expected, market_premium=market_excess)


def _normalise_weights(weights: np.ndarray) -> np.ndarray:
    total = np.sum(weights)
    if np.isclose(total, 0):
        raise ValueError("Sum of weights is zero; cannot normalise.")
    return weights / total


def _max_sharpe_objective(
    weights: np.ndarray,
    expected_returns: np.ndarray,
    cov_matrix: np.ndarray,
    risk_free_rate: float,
) -> float:
    portfolio_return = np.dot(weights, expected_returns)
    portfolio_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
    if np.isclose(portfolio_vol, 0):
        return np.inf
    sharpe_ratio = (portfolio_return - risk_free_rate) / portfolio_vol
    return -sharpe_ratio  # negative for maximisation


def _constraints_long_only(n_assets: int) -> Tuple[Dict, Dict]:
    return (
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},
        {"type": "ineq", "fun": lambda w: w},
    )


def optimise_max_sharpe(
    expected_returns: pd.Series,
    cov_matrix: pd.DataFrame,
    risk_free_rate: float,
    allow_short: bool = False,
) -> pd.Series:
    """
    Compute the maximum Sharpe ratio (tangency) portfolio.

    Args:
        expected_returns: Series of expected returns (CAPM or otherwise).
        cov_matrix: Covariance matrix of asset returns.
        risk_free_rate: Risk-free rate for Sharpe computation.
        allow_short: If False, imposes long-only constraint.

    Returns:
        Series of optimal portfolio weights indexed by asset.
    """

    n_assets = len(expected_returns)
    initial_weights = np.repeat(1 / n_assets, n_assets)

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = None if allow_short else [(0, 1) for _ in range(n_assets)]

    result = minimize(
        _max_sharpe_objective,
        x0=initial_weights,
        args=(expected_returns.values, cov_matrix.values, risk_free_rate),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 500, "disp": False},
    )

    if not result.success:
        raise RuntimeError(f"Optimisation failed: {result.message}")

    weights = pd.Series(result.x, index=expected_returns.index)
    return weights if allow_short else weights.clip(lower=0) / weights.sum()


def minimise_variance(
    cov_matrix: pd.DataFrame,
    target_return: Optional[float] = None,
    expected_returns: Optional[pd.Series] = None,
    allow_short: bool = False,
) -> pd.Series:
    """
    Minimum variance optimisation with optional target return.

    Args:
        cov_matrix: Covariance matrix of asset returns.
        target_return: Desired portfolio return (annualised).
        expected_returns: Series of expected returns (required if target_return provided).
        allow_short: Whether to allow short positions.

    Returns:
        Series of portfolio weights.
    """

    n_assets = cov_matrix.shape[0]
    initial_weights = np.repeat(1 / n_assets, n_assets)

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    if target_return is not None:
        if expected_returns is None:
            raise ValueError("expected_returns must be provided when target_return is set.")
        constraints.append(
            {
                "type": "eq",
                "fun": lambda w: np.dot(w, expected_returns.values) - target_return,
            }
        )

    bounds = None if allow_short else [(0, 1) for _ in range(n_assets)]

    result = minimize(
        lambda w, cov: np.dot(w.T, np.dot(cov, w)),
        x0=initial_weights,
        args=(cov_matrix.values,),
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 500, "disp": False},
    )

    if not result.success:
        raise RuntimeError(f"Optimisation failed: {result.message}")

    weights = pd.Series(result.x, index=cov_matrix.index)
    return weights if allow_short else weights.clip(lower=0) / weights.sum()


def generate_capm_portfolio_summary(
    dataset: CapmDataset,
    allow_short: bool = False,
) -> Dict[str, pd.Series]:
    """
    Produce tangency and minimum-variance portfolios derived from CAPM estimates.

    Args:
        dataset: CAPM dataset (returns + risk-free rate).
        allow_short: Whether optimisation allows short selling.

    Returns:
        Dictionary with betas, expected returns, cov matrix,
        max Sharpe weights, and minimum variance weights.
    """

    summary = summarise_capm(dataset)
    cov_matrix = dataset.asset_returns.cov() * 252  # annualise

    max_sharpe_weights = optimise_max_sharpe(
        expected_returns=summary.expected_returns,
        cov_matrix=cov_matrix,
        risk_free_rate=dataset.risk_free_rate,
        allow_short=allow_short,
    )

    min_var_weights = minimise_variance(
        cov_matrix=cov_matrix,
        allow_short=allow_short,
    )

    return {
        "betas": summary.betas,
        "expected_returns": summary.expected_returns,
        "market_premium": pd.Series([summary.market_premium], index=["market_premium"]),
        "covariance": cov_matrix,
        "max_sharpe_weights": max_sharpe_weights,
        "min_variance_weights": min_var_weights,
    }


__all__ = [
    "CapmSummary",
    "calculate_beta",
    "capm_expected_returns",
    "generate_capm_portfolio_summary",
    "minimise_variance",
    "optimise_max_sharpe",
    "summarise_capm",
]

