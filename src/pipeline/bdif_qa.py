"""Quality assurance module for BDIF holdings data."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

import pandas as pd


@dataclass
class QAResult:
    fund_id: str
    as_of: str
    n_positions: int
    weight_sum: float
    missing_isin: int
    top10_concentration: float
    status: str
    checks_passed: List[str]
    checks_failed: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


class BDIFQualityAssurance:
    WEIGHT_SUM_MIN = 99.5
    WEIGHT_SUM_MAX = 100.5
    MIN_ISIN_COVERAGE = 98.0

    def __init__(self, qa_output_dir: Path):
        self.qa_output_dir = qa_output_dir
        self.qa_output_dir.mkdir(parents=True, exist_ok=True)

    def validate_holdings(self, df: pd.DataFrame, fund_id: str, as_of: str) -> QAResult:
        if df.empty:
            result = QAResult(
                fund_id=fund_id,
                as_of=as_of,
                n_positions=0,
                weight_sum=0.0,
                missing_isin=0,
                top10_concentration=0.0,
                status="fail",
                checks_passed=[],
                checks_failed=["Empty holdings data"],
            )
            self._write_report(result)
            return result

        checks_passed = []
        checks_failed = []

        weight_sum = 0.0
        if "weight_pct" in df.columns:
            weight_sum = float(df["weight_pct"].sum())
            if self.WEIGHT_SUM_MIN <= weight_sum <= self.WEIGHT_SUM_MAX:
                checks_passed.append(f"Weight sum OK: {weight_sum:.2f}%")
            else:
                checks_failed.append(
                    f"Weight sum out of range: {weight_sum:.2f}%"
                )
        else:
            checks_failed.append("Missing weight_pct column")

        missing_isin = int(df["isin"].isna().sum()) if "isin" in df.columns else len(df)
        coverage_pct = 100.0 - (missing_isin / len(df)) * 100.0
        if coverage_pct >= self.MIN_ISIN_COVERAGE:
            checks_passed.append(f"ISIN coverage OK: {coverage_pct:.1f}%")
        else:
            checks_failed.append(f"Low ISIN coverage: {coverage_pct:.1f}%")

        top10_concentration = 0.0
        if "weight_pct" in df.columns:
            top10_concentration = float(
                df.sort_values("weight_pct", ascending=False)
                .head(10)["weight_pct"]
                .sum()
            )
            checks_passed.append(f"Top 10 concentration: {top10_concentration:.2f}%")

        status = "pass" if not checks_failed else "fail"

        result = QAResult(
            fund_id=fund_id,
            as_of=as_of,
            n_positions=len(df),
            weight_sum=weight_sum,
            missing_isin=missing_isin,
            top10_concentration=top10_concentration,
            status=status,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
        )

        self._write_report(result)
        return result

    def _write_report(self, result: QAResult) -> None:
        report_dir = self.qa_output_dir / f"fund_id={result.fund_id}" / f"as_of={result.as_of}"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "qa_report.json"

        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(result.to_dict(), handle, indent=2)

        print(f"\nQA Report saved to {report_path}")
        print(f"Status: {result.status.upper()}")
