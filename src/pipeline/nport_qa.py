"""Quality assurance module for N-PORT holdings data."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List
import pandas as pd


@dataclass
class QAResult:
    """QA validation result."""
    
    fund_id: str
    as_of: str
    n_positions: int
    weight_sum: float
    unresolved_ids: int
    unresolved_pct: float
    top10_concentration: float
    top10_holdings: List[dict]
    checks_passed: List[str]
    checks_failed: List[str]
    status: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)


class NPORTQualityAssurance:
    """Quality assurance for holdings data."""
    
    # QA thresholds
    WEIGHT_SUM_MIN = 99.5
    WEIGHT_SUM_MAX = 100.5
    MIN_IDENTIFIER_COVERAGE = 98.0
    
    def __init__(self, qa_output_dir: Path):
        """Initialize QA module.
        
        Args:
            qa_output_dir: Directory to write QA reports
        """
        self.qa_output_dir = qa_output_dir
        self.qa_output_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_holdings(
        self,
        df: pd.DataFrame,
        fund_id: str,
        as_of: str,
    ) -> QAResult:
        """Run quality checks on holdings data.
        
        Args:
            df: Holdings DataFrame
            fund_id: Fund identifier
            as_of: Report date
            
        Returns:
            QA result object
        """
        if df.empty:
            return QAResult(
                fund_id=fund_id,
                as_of=as_of,
                n_positions=0,
                weight_sum=0.0,
                unresolved_ids=0,
                unresolved_pct=0.0,
                top10_concentration=0.0,
                top10_holdings=[],
                checks_passed=[],
                checks_failed=['Empty holdings data'],
                status='fail',
            )
        
        checks_passed = []
        checks_failed = []
        
        # Check 1: Weight sum
        if 'weight_pct' in df.columns:
            weight_sum = df['weight_pct'].sum()
            if self.WEIGHT_SUM_MIN <= weight_sum <= self.WEIGHT_SUM_MAX:
                checks_passed.append(f"Weight sum OK: {weight_sum:.2f}%")
            else:
                checks_failed.append(
                    f"Weight sum out of range: {weight_sum:.2f}% "
                    f"(expected {self.WEIGHT_SUM_MIN}-{self.WEIGHT_SUM_MAX}%)"
                )
        else:
            weight_sum = 0.0
            checks_failed.append("Missing weight_pct column")
        
        # Check 2: Identifier coverage
        unresolved = 0
        if 'isin' in df.columns and 'cusip' in df.columns:
            unresolved = (df['isin'].isna() & df['cusip'].isna()).sum()
        elif 'isin' in df.columns:
            unresolved = df['isin'].isna().sum()
        elif 'cusip' in df.columns:
            unresolved = df['cusip'].isna().sum()
        
        unresolved_pct = (unresolved / len(df)) * 100.0
        coverage_pct = 100.0 - unresolved_pct
        
        if coverage_pct >= self.MIN_IDENTIFIER_COVERAGE:
            checks_passed.append(
                f"Identifier coverage OK: {coverage_pct:.1f}% "
                f"({len(df) - unresolved}/{len(df)} positions)"
            )
        else:
            checks_failed.append(
                f"Low identifier coverage: {coverage_pct:.1f}% "
                f"(expected >={self.MIN_IDENTIFIER_COVERAGE}%)"
            )
        
        # Check 3: Top 10 concentration
        if 'weight_pct' in df.columns:
            df_sorted = df.sort_values('weight_pct', ascending=False)
            top10_concentration = df_sorted.head(10)['weight_pct'].sum()
            checks_passed.append(f"Top 10 concentration: {top10_concentration:.2f}%")
            
            # Extract top 10 for report
            top10_holdings = []
            for idx, row in df_sorted.head(10).iterrows():
                top10_holdings.append({
                    'name': str(row.get('instrument_name', row.get('instrument_name_raw', 'Unknown'))),
                    'isin': str(row.get('isin', '')),
                    'weight_pct': float(row.get('weight_pct', 0.0)),
                })
        else:
            top10_concentration = 0.0
            top10_holdings = []
        
        # Check 4: Data completeness
        required_cols = ['instrument_name_raw', 'market_value_local', 'as_of', 'fund_id']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if not missing_cols:
            checks_passed.append("All required columns present")
        else:
            checks_failed.append(f"Missing columns: {', '.join(missing_cols)}")
        
        # Determine overall status
        status = 'pass' if not checks_failed else 'fail'
        
        result = QAResult(
            fund_id=fund_id,
            as_of=as_of,
            n_positions=len(df),
            weight_sum=weight_sum,
            unresolved_ids=unresolved,
            unresolved_pct=unresolved_pct,
            top10_concentration=top10_concentration,
            top10_holdings=top10_holdings,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            status=status,
        )
        
        # Write QA report
        self._write_report(result)
        
        return result
    
    def _write_report(self, result: QAResult) -> None:
        """Write QA report to JSON file.
        
        Args:
            result: QA result
        """
        report_dir = self.qa_output_dir / f"fund_id={result.fund_id}" / f"as_of={result.as_of}"
        report_dir.mkdir(parents=True, exist_ok=True)
        
        report_path = report_dir / "qa_report.json"
        
        with report_path.open('w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, indent=2)
        
        print(f"\nQA Report saved to {report_path}")
        print(f"Status: {result.status.upper()}")
        print(f"Positions: {result.n_positions}")
        print(f"Weight sum: {result.weight_sum:.2f}%")
        
        if result.checks_passed:
            print("\nPassed checks:")
            for check in result.checks_passed:
                print(f"  ✓ {check}")
        
        if result.checks_failed:
            print("\nFailed checks:")
            for check in result.checks_failed:
                print(f"  ✗ {check}")

