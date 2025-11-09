"""
Performance Metrics and Statistics Module

This module provides functions to calculate various portfolio performance
metrics, risk measures, and statistical analyses.
"""

from typing import Dict, Optional

import numpy as np
import pandas as pd


def calculate_returns(prices: pd.Series, period: str = "daily") -> pd.Series:
    """
    Calculates returns from a price series.

    Args:
        prices: A pandas Series of prices.
        period: Return period ('daily', 'monthly', 'yearly').

    Returns:
        A Series of returns.
    """
    return prices.pct_change().dropna()


def calculate_cumulative_returns(returns: pd.Series) -> pd.Series:
    """
    Calculates cumulative returns from a return series.

    Args:
        returns: A pandas Series of returns.

    Returns:
        A Series of cumulative returns.
    """
    return (1 + returns).cumprod() - 1


def calculate_annualized_return(
    returns: pd.Series, periods_per_year: int = 252
) -> float:
    """
    Calculates the annualized return from a return series.

    Args:
        returns: A pandas Series of returns.
        periods_per_year: Number of periods per year (252 for daily, 12 for monthly).

    Returns:
        Annualized return as a decimal.
    """
    total_return = (1 + returns).prod()
    n_periods = len(returns)
    annualized = total_return ** (periods_per_year / n_periods) - 1
    return annualized


def calculate_volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    """
    Calculates annualized volatility (standard deviation).

    Args:
        returns: A pandas Series of returns.
        periods_per_year: Number of periods per year.

    Returns:
        Annualized volatility as a decimal.
    """
    return returns.std() * np.sqrt(periods_per_year)


def calculate_sharpe_ratio(
    returns: pd.Series, risk_free_rate: float = 0.02, periods_per_year: int = 252
) -> float:
    """
    Calculates the Sharpe ratio.

    Args:
        returns: A pandas Series of returns.
        risk_free_rate: Annual risk-free rate as a decimal.
        periods_per_year: Number of periods per year.

    Returns:
        The Sharpe ratio.
    """
    excess_returns = returns - (risk_free_rate / periods_per_year)
    return np.sqrt(periods_per_year) * excess_returns.mean() / returns.std()


def calculate_max_drawdown(returns: pd.Series) -> Dict[str, float]:
    """
    Calculates the maximum drawdown and related metrics.

    Args:
        returns: A pandas Series of returns.

    Returns:
        A dictionary with max drawdown, peak, and trough information.
    """
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max

    max_dd = drawdown.min()
    max_dd_idx = drawdown.idxmin()
    peak_idx = cumulative[:max_dd_idx].idxmax()

    return {
        "Max_Drawdown": max_dd,
        "Peak_Date": peak_idx,
        "Trough_Date": max_dd_idx,
        "Drawdown_Series": drawdown,
    }


def calculate_sortino_ratio(
    returns: pd.Series, risk_free_rate: float = 0.02, periods_per_year: int = 252
) -> float:
    """
    Calculates the Sortino ratio (uses downside deviation).

    Args:
        returns: A pandas Series of returns.
        risk_free_rate: Annual risk-free rate as a decimal.
        periods_per_year: Number of periods per year.

    Returns:
        The Sortino ratio.
    """
    excess_returns = returns - (risk_free_rate / periods_per_year)
    downside_returns = returns[returns < 0]
    downside_std = downside_returns.std() * np.sqrt(periods_per_year)

    if downside_std == 0:
        return np.inf

    return (excess_returns.mean() * periods_per_year) / downside_std


def calculate_calmar_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    """
    Calculates the Calmar ratio (return / max drawdown).

    Args:
        returns: A pandas Series of returns.
        periods_per_year: Number of periods per year.

    Returns:
        The Calmar ratio.
    """
    annual_return = calculate_annualized_return(returns, periods_per_year)
    max_dd = calculate_max_drawdown(returns)["Max_Drawdown"]

    if max_dd == 0:
        return np.inf

    return annual_return / abs(max_dd)


def calculate_information_ratio(
    returns: pd.Series, benchmark_returns: pd.Series, periods_per_year: int = 252
) -> float:
    """
    Calculates the information ratio (excess return / tracking error).

    Args:
        returns: A pandas Series of portfolio returns.
        benchmark_returns: A pandas Series of benchmark returns.
        periods_per_year: Number of periods per year.

    Returns:
        The information ratio.
    """
    excess_returns = returns - benchmark_returns
    tracking_error = excess_returns.std() * np.sqrt(periods_per_year)

    if tracking_error == 0:
        return np.inf

    return (excess_returns.mean() * periods_per_year) / tracking_error


def calculate_beta(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """
    Calculates portfolio beta relative to a benchmark.

    Args:
        returns: A pandas Series of portfolio returns.
        benchmark_returns: A pandas Series of benchmark returns.

    Returns:
        The beta coefficient.
    """
    covariance = returns.cov(benchmark_returns)
    benchmark_variance = benchmark_returns.var()

    if benchmark_variance == 0:
        return 0

    return covariance / benchmark_variance


def calculate_alpha(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> float:
    """
    Calculates Jensen's alpha.

    Args:
        returns: A pandas Series of portfolio returns.
        benchmark_returns: A pandas Series of benchmark returns.
        risk_free_rate: Annual risk-free rate as a decimal.
        periods_per_year: Number of periods per year.

    Returns:
        Jensen's alpha as an annualized value.
    """
    beta = calculate_beta(returns, benchmark_returns)

    portfolio_return = calculate_annualized_return(returns, periods_per_year)
    benchmark_return = calculate_annualized_return(benchmark_returns, periods_per_year)

    expected_return = risk_free_rate + beta * (benchmark_return - risk_free_rate)
    alpha = portfolio_return - expected_return

    return alpha


def generate_performance_report(
    returns: pd.Series,
    benchmark_returns: Optional[pd.Series] = None,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> Dict:
    """
    Generates a comprehensive performance report.

    Args:
        returns: A pandas Series of portfolio returns.
        benchmark_returns: Optional benchmark returns for relative metrics.
        risk_free_rate: Annual risk-free rate as a decimal.
        periods_per_year: Number of periods per year.

    Returns:
        A dictionary with all performance metrics.
    """
    report = {
        "Total_Return": (1 + returns).prod() - 1,
        "Annualized_Return": calculate_annualized_return(returns, periods_per_year),
        "Annualized_Volatility": calculate_volatility(returns, periods_per_year),
        "Sharpe_Ratio": calculate_sharpe_ratio(
            returns, risk_free_rate, periods_per_year
        ),
        "Sortino_Ratio": calculate_sortino_ratio(
            returns, risk_free_rate, periods_per_year
        ),
        "Calmar_Ratio": calculate_calmar_ratio(returns, periods_per_year),
        "Max_Drawdown": calculate_max_drawdown(returns)["Max_Drawdown"],
        "Max_Drawdown_Peak": calculate_max_drawdown(returns)["Peak_Date"],
        "Max_Drawdown_Trough": calculate_max_drawdown(returns)["Trough_Date"],
    }

    if benchmark_returns is not None:
        report["Beta"] = calculate_beta(returns, benchmark_returns)
        report["Alpha"] = calculate_alpha(
            returns, benchmark_returns, risk_free_rate, periods_per_year
        )
        report["Information_Ratio"] = calculate_information_ratio(
            returns, benchmark_returns, periods_per_year
        )

    return report


def print_performance_report(report: Dict):
    """
    Prints a formatted performance report.

    Args:
        report: A dictionary of performance metrics.
    """
    print("\n" + "=" * 60)
    print("PERFORMANCE REPORT")
    print("=" * 60)

    print("\nReturn Metrics:")
    print(f"  Total Return:           {report['Total_Return']:>12.2%}")
    print(f"  Annualized Return:      {report['Annualized_Return']:>12.2%}")

    print("\nRisk Metrics:")
    print(f"  Annualized Volatility:  {report['Annualized_Volatility']:>12.2%}")
    print(f"  Maximum Drawdown:       {report['Max_Drawdown']:>12.2%}")
    print(f"    Peak Date:            {str(report['Max_Drawdown_Peak'])[:10]:>12}")
    print(f"    Trough Date:          {str(report['Max_Drawdown_Trough'])[:10]:>12}")

    print("\nRisk-Adjusted Metrics:")
    print(f"  Sharpe Ratio:           {report['Sharpe_Ratio']:>12.2f}")
    print(f"  Sortino Ratio:          {report['Sortino_Ratio']:>12.2f}")
    print(f"  Calmar Ratio:           {report['Calmar_Ratio']:>12.2f}")

    if "Beta" in report:
        print("\nBenchmark-Relative Metrics:")
        print(f"  Beta:                   {report['Beta']:>12.2f}")
        print(f"  Alpha (annualized):     {report['Alpha']:>12.2%}")
        print(f"  Information Ratio:      {report['Information_Ratio']:>12.2f}")

    print("\n" + "=" * 60 + "\n")
