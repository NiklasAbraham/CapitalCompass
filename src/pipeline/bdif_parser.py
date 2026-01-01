"""BDIF PDF parser for French UCITS holdings."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
import pdfplumber


@dataclass
class Holding:
    """Represents a single portfolio holding from BDIF report."""

    as_of: str
    fund_id: str
    designation: str
    isin: Optional[str] = None
    cusip: Optional[str] = None
    quantity: Optional[float] = None
    market_value_eur: Optional[float] = None
    weight_pct: Optional[float] = None
    country_raw: Optional[str] = None
    asset_class_raw: Optional[str] = None
    source_pdf_sha256: Optional[str] = None


class BDIFParser:
    """Parse BDIF PDF reports to extract holdings."""

    HEADER_PATTERN = re.compile(
        r"(?i)(composition de l'?actif|portefeuille titres)"
    )

    def parse_report(self, pdf_path: Path, fund_id: str) -> tuple[List[Holding], dict]:
        """Parse a BDIF PDF report.

        Args:
            pdf_path: Path to PDF file
            fund_id: Fund identifier

        Returns:
            Tuple of (holdings list, metadata dict)
        """
        print(f"Parsing {pdf_path}...")

        holdings: List[Holding] = []
        as_of_date: Optional[str] = None

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if not self.HEADER_PATTERN.search(text):
                    continue

                if not as_of_date:
                    as_of_date = self._extract_date_from_text(text)

                tables = page.extract_tables()
                for table in tables:
                    holdings.extend(
                        self._parse_table(table, fund_id, as_of_date)
                    )

                if holdings:
                    print(f"Found holdings section on page {page_num + 1}")
                    break

        if not as_of_date:
            as_of_date = self._extract_date_from_path(pdf_path)
        if not as_of_date:
            as_of_date = datetime.now().strftime("%Y-%m-%d")

        sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        for holding in holdings:
            holding.as_of = as_of_date
            holding.source_pdf_sha256 = sha

        metadata = {
            "as_of": as_of_date,
            "fund_id": fund_id,
            "n_holdings": len(holdings),
            "source_file": str(pdf_path),
            "source_pdf_sha256": sha,
        }

        print(f"Extracted {len(holdings)} holdings")
        return holdings, metadata

    def _extract_date_from_text(self, text: str) -> Optional[str]:
        patterns = [
            r"(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})",
            r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
            r"(\d{4})-(\d{1,2})-(\d{1,2})",
        ]

        month_map_fr = {
            "janvier": 1,
            "février": 2,
            "fevrier": 2,
            "mars": 3,
            "avril": 4,
            "mai": 5,
            "juin": 6,
            "juillet": 7,
            "août": 8,
            "aout": 8,
            "septembre": 9,
            "octobre": 10,
            "novembre": 11,
            "décembre": 12,
            "decembre": 12,
        }
        month_map_en = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            if pattern.startswith(r"(\\d{4})"):
                year, month, day = match.groups()
                return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
            day, month_name, year = match.groups()
            month_name_lower = month_name.lower()
            month = month_map_fr.get(month_name_lower) or month_map_en.get(month_name_lower)
            if month:
                return datetime(int(year), month, int(day)).strftime("%Y-%m-%d")
        return None

    def _extract_date_from_path(self, pdf_path: Path) -> Optional[str]:
        match = re.search(r"as_of=(\\d{4}-\\d{2}-\\d{2})", str(pdf_path))
        if match:
            return match.group(1)
        return None

    def _parse_table(
        self,
        table: List[List],
        fund_id: str,
        as_of_date: Optional[str],
    ) -> List[Holding]:
        if not table or len(table) < 2:
            return []

        header_idx = self._find_header_row(table)
        if header_idx is None:
            return []

        headers = [
            str(cell).strip().lower() if cell else "" for cell in table[header_idx]
        ]
        mapping = self._map_columns(headers)

        holdings: List[Holding] = []
        for row in table[header_idx + 1 :]:
            if not row or all(not cell or str(cell).strip() == "" for cell in row):
                continue

            designation_idx = mapping.get("designation")
            if designation_idx is None or designation_idx >= len(row):
                continue
            designation = str(row[designation_idx]).strip()
            if not designation or designation.lower().startswith("total"):
                continue

            isin = self._extract_isin(row, mapping)
            quantity = self._extract_float(row, mapping.get("quantity"))
            market_value = self._extract_float(row, mapping.get("value"))
            weight_pct = self._extract_float(row, mapping.get("weight"))
            country_raw = self._extract_text(row, mapping.get("country"))
            asset_class_raw = self._extract_text(row, mapping.get("asset_class"))

            holdings.append(
                Holding(
                    as_of=as_of_date or datetime.now().strftime("%Y-%m-%d"),
                    fund_id=fund_id,
                    designation=designation,
                    isin=isin,
                    quantity=quantity,
                    market_value_eur=market_value,
                    weight_pct=weight_pct,
                    country_raw=country_raw,
                    asset_class_raw=asset_class_raw,
                )
            )

        return holdings

    def _find_header_row(self, table: List[List]) -> Optional[int]:
        header_keywords = [
            "designation",
            "désignation",
            "libellé",
            "isin",
            "quantité",
            "quantity",
            "valeur",
            "value",
            "montant",
            "%", 
            "poids",
            "country",
            "pays",
        ]

        for idx, row in enumerate(table[:10]):
            row_text = " ".join(str(cell).lower() if cell else "" for cell in row)
            matches = sum(1 for kw in header_keywords if kw in row_text)
            if matches >= 2:
                return idx
        return 0

    def _map_columns(self, headers: List[str]) -> dict:
        mapping = {}

        for idx, header in enumerate(headers):
            if any(term in header for term in ["designation", "désignation", "libellé", "intitul"]):
                mapping["designation"] = idx
            elif "isin" in header:
                mapping["isin"] = idx
            elif any(term in header for term in ["quantité", "quantity", "nombre", "shares"]):
                mapping["quantity"] = idx
            elif any(term in header for term in ["valeur", "value", "montant", "market"]):
                mapping["value"] = idx
            elif "%" in header or "poids" in header:
                mapping["weight"] = idx
            elif any(term in header for term in ["pays", "country"]):
                mapping["country"] = idx
            elif any(term in header for term in ["classe", "asset", "type", "categorie", "catégorie"]):
                mapping["asset_class"] = idx

        return mapping

    def _extract_isin(self, row: List, mapping: dict) -> Optional[str]:
        idx = mapping.get("isin")
        if idx is None or idx >= len(row):
            return None
        value = str(row[idx]).strip().upper()
        if len(value) == 12 and value[:2].isalpha() and value[2:].isalnum():
            return value
        return None

    def _extract_text(self, row: List, idx: Optional[int]) -> Optional[str]:
        if idx is None or idx >= len(row):
            return None
        value = row[idx]
        if value is None:
            return None
        return str(value).strip()

    def _extract_float(self, row: List, idx: Optional[int]) -> Optional[float]:
        if idx is None or idx >= len(row):
            return None
        return self._parse_float(str(row[idx]))

    def _parse_float(self, value: Optional[str]) -> Optional[float]:
        if not value:
            return None
        value = value.strip()
        value = value.replace("\u00a0", "").replace(" ", "")
        value = value.replace("€", "").replace("%", "")

        if value.count(",") == 1 and value.count(".") == 0:
            value = value.replace(",", ".")
        elif value.count(",") > 1 and value.count(".") == 0:
            value = value.replace(",", "")
        else:
            value = value.replace(",", "")

        if value.startswith("(") and value.endswith(")"):
            value = "-" + value[1:-1]

        try:
            return float(value)
        except ValueError:
            return None

    def to_dataframe(self, holdings: List[Holding]) -> pd.DataFrame:
        if not holdings:
            return pd.DataFrame()
        data = [asdict(holding) for holding in holdings]
        return pd.DataFrame(data)
