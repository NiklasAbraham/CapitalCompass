"""OAM PDF parser for extracting holdings from UCITS financial reports.

Parses PDF reports from Luxembourg and German OAM sources to extract
the "Statement of Investments" table.
"""

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
    """Represents a single portfolio holding from OAM report."""
    
    as_of: str
    fund_id: str
    instrument_name_raw: str
    isin: Optional[str] = None
    quantity: Optional[float] = None
    market_value_local: Optional[float] = None
    currency: Optional[str] = None
    category_raw: Optional[str] = None
    country_raw: Optional[str] = None
    derivative_flag: bool = False
    source_doc_id: Optional[str] = None
    source_url: Optional[str] = None
    parse_hash: Optional[str] = None


class OAMParser:
    """Parse OAM PDF reports to extract holdings."""
    
    def __init__(self):
        """Initialize parser."""
        pass
    
    def parse_report(
        self,
        pdf_path: Path,
        fund_id: str,
        source_url: Optional[str] = None,
    ) -> tuple[List[Holding], dict]:
        """Parse an OAM PDF report.
        
        Args:
            pdf_path: Path to the PDF file
            fund_id: Fund identifier
            source_url: Source URL of the report
            
        Returns:
            Tuple of (holdings list, metadata dict)
        """
        print(f"Parsing {pdf_path}...")
        
        try:
            holdings = []
            as_of_date = None
            
            with pdfplumber.open(pdf_path) as pdf:
                # Search for the holdings table
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    text_lower = text.lower()
                    
                    # Look for indicators of holdings table
                    if any(
                        keyword in text_lower
                        for keyword in [
                            "portfolio of investments",
                            "statement of investments",
                            "list of investments",
                            "investments",
                            "holdings",
                        ]
                    ):
                        print(f"Found holdings section on page {page_num + 1}")
                        
                        # Try to extract date from this page
                        if not as_of_date:
                            as_of_date = self._extract_date_from_text(text)
                        
                        # Extract table
                        tables = page.extract_tables()
                        for table in tables:
                            parsed_holdings = self._parse_table(table, fund_id, as_of_date, source_url)
                            holdings.extend(parsed_holdings)
                        
                        # Also try to extract from text if table extraction failed
                        if not holdings:
                            holdings = self._parse_text_holdings(text, fund_id, as_of_date, source_url)
            
            # If no date found, try to extract from filename or use current date
            if not as_of_date:
                as_of_date = self._extract_date_from_path(pdf_path)
                if not as_of_date:
                    as_of_date = datetime.now().strftime("%Y-%m-%d")
            
            # Update all holdings with the date
            for holding in holdings:
                holding.as_of = as_of_date
            
            # Generate parse hash
            parse_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:16]
            for holding in holdings:
                holding.parse_hash = parse_hash
            
            metadata = {
                "as_of": as_of_date,
                "fund_id": fund_id,
                "n_holdings": len(holdings),
                "parse_hash": parse_hash,
                "source_file": str(pdf_path),
            }
            
            print(f"Extracted {len(holdings)} holdings")
            return holdings, metadata
            
        except Exception as e:
            print(f"Failed to parse PDF: {e}")
            import traceback
            traceback.print_exc()
            return [], {"error": str(e)}
    
    def _extract_date_from_text(self, text: str) -> Optional[str]:
        """Extract date from text content.
        
        Args:
            text: Text to search
            
        Returns:
            Date as YYYY-MM-DD or None
        """
        # Look for common date patterns
        patterns = [
            r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
            r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})",  # DD.MM.YYYY
            r"(\d{4})-(\d{1,2})-(\d{1,2})",  # YYYY-MM-DD
            r"as\s+of\s+(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    if len(match.groups()) == 3:
                        if "as of" in pattern.lower() or any(
                            month in match.group(0).lower()
                            for month in ["january", "february", "march", "april", "may", "june",
                                        "july", "august", "september", "october", "november", "december"]
                        ):
                            # Month name format
                            day, month_name, year = match.groups()
                            month_map = {
                                "january": 1, "february": 2, "march": 3, "april": 4,
                                "may": 5, "june": 6, "july": 7, "august": 8,
                                "september": 9, "october": 10, "november": 11, "december": 12,
                            }
                            month = month_map.get(month_name.lower())
                            if month:
                                dt = datetime(int(year), month, int(day))
                                return dt.strftime("%Y-%m-%d")
                        elif "." in pattern:
                            # DD.MM.YYYY format
                            day, month, year = match.groups()
                            dt = datetime(int(year), int(month), int(day))
                            return dt.strftime("%Y-%m-%d")
                        elif "-" in pattern:
                            # YYYY-MM-DD format
                            year, month, day = match.groups()
                            dt = datetime(int(year), int(month), int(day))
                            return dt.strftime("%Y-%m-%d")
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _extract_date_from_path(self, pdf_path: Path) -> Optional[str]:
        """Extract date from file path.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Date as YYYY-MM-DD or None
        """
        # Look for as_of=YYYY-MM-DD in path
        match = re.search(r"as_of=(\d{4}-\d{2}-\d{2})", str(pdf_path))
        if match:
            return match.group(1)
        return None
    
    def _parse_table(self, table: List[List], fund_id: str, as_of_date: Optional[str], source_url: Optional[str]) -> List[Holding]:
        """Parse a table structure into holdings.
        
        Args:
            table: Table data as list of rows
            fund_id: Fund identifier
            as_of_date: Report date
            source_url: Source URL
            
        Returns:
            List of holdings
        """
        if not table or len(table) < 2:
            return []
        
        holdings = []
        
        # Try to identify header row
        header_row_idx = self._find_header_row(table)
        if header_row_idx is None:
            return []
        
        headers = [str(cell).strip().lower() if cell else "" for cell in table[header_row_idx]]
        
        # Map common column names
        col_mapping = self._map_columns(headers)
        
        # Parse data rows
        for row_idx in range(header_row_idx + 1, len(table)):
            row = table[row_idx]
            if not row or all(not cell or str(cell).strip() == "" for cell in row):
                continue
            
            holding = self._parse_table_row(row, headers, col_mapping, fund_id, as_of_date, source_url)
            if holding:
                holdings.append(holding)
        
        return holdings
    
    def _find_header_row(self, table: List[List]) -> Optional[int]:
        """Find the header row in a table.
        
        Args:
            table: Table data
            
        Returns:
            Index of header row or None
        """
        header_keywords = [
            "name", "instrument", "security", "issuer",
            "isin", "quantity", "shares", "units",
            "value", "market", "currency", "country",
        ]
        
        for idx, row in enumerate(table[:10]):  # Check first 10 rows
            if not row:
                continue
            
            row_text = " ".join(str(cell).lower() if cell else "" for cell in row)
            matches = sum(1 for keyword in header_keywords if keyword in row_text)
            
            if matches >= 3:  # At least 3 header keywords
                return idx
        
        return 0  # Default to first row
    
    def _map_columns(self, headers: List[str]) -> dict:
        """Map column headers to field names.
        
        Args:
            headers: List of header strings
            
        Returns:
            Dictionary mapping column index to field name
        """
        mapping = {}
        
        for idx, header in enumerate(headers):
            header_lower = header.lower()
            
            if any(kw in header_lower for kw in ["name", "instrument", "security", "issuer", "description"]):
                mapping["name"] = idx
            elif "isin" in header_lower:
                mapping["isin"] = idx
            elif any(kw in header_lower for kw in ["quantity", "shares", "units", "number", "nominal"]):
                mapping["quantity"] = idx
            elif any(kw in header_lower for kw in ["value", "market value", "fair value", "amount"]):
                mapping["value"] = idx
            elif "currency" in header_lower or "cur" in header_lower:
                mapping["currency"] = idx
            elif "country" in header_lower:
                mapping["country"] = idx
            elif any(kw in header_lower for kw in ["category", "type", "asset class", "sector"]):
                mapping["category"] = idx
        
        return mapping
    
    def _parse_table_row(
        self,
        row: List,
        headers: List[str],
        col_mapping: dict,
        fund_id: str,
        as_of_date: Optional[str],
        source_url: Optional[str],
    ) -> Optional[Holding]:
        """Parse a single table row into a holding.
        
        Args:
            row: Table row data
            headers: Column headers
            col_mapping: Column mapping dictionary
            fund_id: Fund identifier
            as_of_date: Report date
            source_url: Source URL
            
        Returns:
            Holding object or None
        """
        # Extract name
        name_idx = col_mapping.get("name")
        if name_idx is None or name_idx >= len(row) or not row[name_idx]:
            return None
        
        name = str(row[name_idx]).strip()
        if not name or name.lower() in ["total", "sum", ""]:
            return None
        
        # Extract other fields
        isin = None
        if "isin" in col_mapping:
            isin_idx = col_mapping["isin"]
            if isin_idx < len(row) and row[isin_idx]:
                isin = str(row[isin_idx]).strip()
                # Validate ISIN format (12 characters, alphanumeric)
                if len(isin) != 12 or not isin[:2].isalpha() or not isin[2:].isalnum():
                    isin = None
        
        quantity = None
        if "quantity" in col_mapping:
            qty_idx = col_mapping["quantity"]
            if qty_idx < len(row) and row[qty_idx]:
                quantity = self._parse_float(str(row[qty_idx]))
        
        market_value = None
        if "value" in col_mapping:
            val_idx = col_mapping["value"]
            if val_idx < len(row) and row[val_idx]:
                market_value = self._parse_float(str(row[val_idx]))
        
        currency = None
        if "currency" in col_mapping:
            curr_idx = col_mapping["currency"]
            if curr_idx < len(row) and row[curr_idx]:
                currency = str(row[curr_idx]).strip().upper()
        
        country = None
        if "country" in col_mapping:
            country_idx = col_mapping["country"]
            if country_idx < len(row) and row[country_idx]:
                country = str(row[country_idx]).strip()
        
        category = None
        if "category" in col_mapping:
            cat_idx = col_mapping["category"]
            if cat_idx < len(row) and row[cat_idx]:
                category = str(row[cat_idx]).strip()
        
        return Holding(
            as_of=as_of_date or datetime.now().strftime("%Y-%m-%d"),
            fund_id=fund_id,
            instrument_name_raw=name,
            isin=isin,
            quantity=quantity,
            market_value_local=market_value,
            currency=currency,
            country_raw=country,
            category_raw=category,
            source_url=source_url,
        )
    
    def _parse_text_holdings(self, text: str, fund_id: str, as_of_date: Optional[str], source_url: Optional[str]) -> List[Holding]:
        """Parse holdings from unstructured text (fallback method).
        
        Args:
            text: Text content
            fund_id: Fund identifier
            as_of_date: Report date
            source_url: Source URL
            
        Returns:
            List of holdings
        """
        # This is a fallback - try to extract ISINs and names from text
        holdings = []
        
        # Look for ISIN patterns
        isin_pattern = r"\b([A-Z]{2}[A-Z0-9]{10})\b"
        isin_matches = re.finditer(isin_pattern, text)
        
        for match in isin_matches:
            isin = match.group(1)
            # Try to find name near the ISIN
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end]
            
            # Extract potential name (text before ISIN)
            lines = context.split("\n")
            name = None
            for line in lines:
                if isin in line:
                    # Name is likely in previous lines
                    name = line.split(isin)[0].strip()
                    if not name:
                        # Try previous line
                        idx = lines.index(line)
                        if idx > 0:
                            name = lines[idx - 1].strip()
                    break
            
            if name:
                holdings.append(
                    Holding(
                        as_of=as_of_date or datetime.now().strftime("%Y-%m-%d"),
                        fund_id=fund_id,
                        instrument_name_raw=name,
                        isin=isin,
                        source_url=source_url,
                    )
                )
        
        return holdings
    
    def _parse_float(self, value: Optional[str]) -> Optional[float]:
        """Parse a string to float.
        
        Args:
            value: String value
            
        Returns:
            Float value or None
        """
        if not value:
            return None
        
        # Remove common formatting
        value = str(value).strip()
        value = value.replace(",", "").replace(" ", "")
        value = value.replace("€", "").replace("$", "").replace("£", "").replace("EUR", "").replace("USD", "")
        
        # Handle negative values in parentheses
        if value.startswith("(") and value.endswith(")"):
            value = "-" + value[1:-1]
        
        try:
            return float(value)
        except (ValueError, AttributeError):
            return None
    
    def to_dataframe(self, holdings: List[Holding]) -> pd.DataFrame:
        """Convert holdings to DataFrame.
        
        Args:
            holdings: List of holdings
            
        Returns:
            DataFrame of holdings
        """
        if not holdings:
            return pd.DataFrame()
        
        data = [asdict(holding) for holding in holdings]
        return pd.DataFrame(data)
