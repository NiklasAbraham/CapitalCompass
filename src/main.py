"""
Capital Compass - Main Entry Point

This script serves as the main executable for the portfolio analysis
and market simulation toolkit.

It orchestrates the workflow by:
1. Importing analysis functions from dedicated modules.
2. Calling those functions to perform calculations.
3. Receiving Figure objects from the analysis modules.
4. Displaying the plots to the user.
"""

import plotly.io as pio

from config import DEFAULT_START_DATE, PORTFOLIO_FILE
from core.market_sim import analyze_index_exclusion
from core.portfolio import analyze_portfolio_composition

# Set Plotly to open plots in the default browser
pio.renderers.default = "browser"


def run_portfolio_analysis(portfolio_file: str = PORTFOLIO_FILE):
    """
    Runs the portfolio composition analysis and displays plots.

    Args:
        portfolio_file: Path to the portfolio configuration JSON file.
    """
    print("\n" + "=" * 70)
    print("PORTFOLIO COMPOSITION ANALYSIS")
    print("=" * 70)

    try:
        fig_asset, fig_sector = analyze_portfolio_composition(portfolio_file)

        if fig_asset:
            print("\nDisplaying Asset Allocation plot...")
            fig_asset.show()

        if fig_sector:
            print("Displaying Sector Allocation plot...")
            fig_sector.show()

        print("\nPortfolio analysis complete.")

    except FileNotFoundError:
        print(f"\nERROR: {portfolio_file} not found.")
        print("Please ensure the portfolio configuration file exists.")
    except Exception as e:
        print(f"\nAn error occurred during portfolio analysis: {e}")
        import traceback

        traceback.print_exc()


def run_simulation_analysis(
    exclusion_list: list = None, start_date: str = DEFAULT_START_DATE
):
    """
    Defines simulation parameters and runs the index exclusion analysis.

    Args:
        exclusion_list: List of ticker symbols to exclude from simulation.
        start_date: Start date for the simulation (YYYY-MM-DD).
    """
    print("\n" + "=" * 70)
    print("INDEX COUNTERFACTUAL SIMULATION")
    print("=" * 70)

    if exclusion_list is None:
        # Default: "The Magnificent 7"
        exclusion_list = [
            "AAPL",
            "MSFT",
            "GOOG",
            "GOOGL",
            "AMZN",
            "NVDA",
            "META",
            "TSLA",
        ]

    print("\nSimulation Parameters:")
    print(f"  Start Date: {start_date}")
    print(f"  Exclusion List ({len(exclusion_list)}): {', '.join(exclusion_list)}")

    try:
        fig_sim = analyze_index_exclusion(
            exclusion_list=exclusion_list, start_date=start_date
        )

        if fig_sim:
            print("\nDisplaying simulation plot...")
            fig_sim.show()
            print("\nIndex simulation complete.")
        else:
            print("\nSimulation failed. Check error messages above.")

    except Exception as e:
        print(f"\nAn error occurred during index simulation: {e}")
        import traceback

        traceback.print_exc()


def main():
    """
    Main execution block
    """
    print("\n" + "#" * 70)
    print("# CAPITAL COMPASS - Portfolio Analysis & Index Simulation Toolkit")
    print("#" * 70)

    # Task 1: Analyze Personal Portfolio
    run_portfolio_analysis()

    # Task 2: Analyze S&P 500
    run_simulation_analysis()

    print("\n" + "=" * 70)
    print("TOOLKIT RUN COMPLETE")
    print("=" * 70)
    print("\nFor interactive analysis, use the Jupyter notebooks in notebooks/")
    print("  - 01_Portfolio_Analysis.ipynb")
    print("  - 02_Index_Simulation.ipynb")


if __name__ == "__main__":
    main()
