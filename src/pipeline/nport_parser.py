"""SEC Form N-PORT XML parser.

Parses N-PORT XML filings to extract portfolio holdings data.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import pandas as pd


@dataclass
class Holding:
    """Represents a single portfolio holding from N-PORT."""
    
    as_of: str
    fund_id: str
    instrument_name_raw: str
    cusip: Optional[str] = None
    isin: Optional[str] = None
    balance: Optional[float] = None
    market_value_local: Optional[float] = None
    currency: Optional[str] = None
    category_raw: Optional[str] = None
    country_raw: Optional[str] = None
    derivative_flag: bool = False
    issuer_name: Optional[str] = None
    maturity: Optional[str] = None
    coupon: Optional[float] = None
    source_doc_id: Optional[str] = None
    source_url: Optional[str] = None
    parse_hash: Optional[str] = None


class NPORTParser:
    """Parse N-PORT XML filings."""
    
    # Common N-PORT XML namespaces
    NAMESPACES = {
        'ns1': 'http://www.sec.gov/edgar/nport',
        'nport': 'http://www.sec.gov/edgar/nport',
        'xbrli': 'http://www.xbrl.org/2003/instance',
        'link': 'http://www.xbrl.org/2003/linkbase',
    }
    
    def __init__(self):
        """Initialize parser."""
        pass
    
    def parse_filing(
        self,
        xml_path: Path,
        fund_id: str,
        source_url: Optional[str] = None,
    ) -> tuple[List[Holding], dict]:
        """Parse an N-PORT XML filing.
        
        Args:
            xml_path: Path to the XML file
            fund_id: Fund identifier
            source_url: Source URL of the filing
            
        Returns:
            Tuple of (holdings list, metadata dict)
        """
        print(f"Parsing {xml_path}...")
        
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
        except ET.ParseError as e:
            print(f"Failed to parse XML: {e}")
            return [], {"error": str(e)}
        
        # Extract report date
        as_of_date = self._extract_report_date(root)
        if not as_of_date:
            print("Warning: Could not extract report date, using current date")
            as_of_date = datetime.now().strftime("%Y-%m-%d")
        
        # Parse holdings
        holdings = self._parse_holdings(root, fund_id, as_of_date, source_url)
        
        # Generate parse hash
        parse_hash = hashlib.sha256(xml_path.read_bytes()).hexdigest()[:16]
        for holding in holdings:
            holding.parse_hash = parse_hash
        
        metadata = {
            "as_of": as_of_date,
            "fund_id": fund_id,
            "n_holdings": len(holdings),
            "parse_hash": parse_hash,
            "source_file": str(xml_path),
        }
        
        print(f"Extracted {len(holdings)} holdings")
        return holdings, metadata
    
    def _extract_report_date(self, root: ET.Element) -> Optional[str]:
        """Extract the report date from N-PORT filing.
        
        Args:
            root: XML root element
            
        Returns:
            Report date as YYYY-MM-DD or None
        """
        # Try multiple possible locations for the report date
        
        # Method 1: Look for reportingPeriodEndDate or repPdEnded
        for tag in ['reportingPeriodEndDate', 'repPdEnded', 'reportDate']:
            for ns_prefix in ['', 'ns1:', 'nport:']:
                elements = root.findall(f".//{ns_prefix}{tag}", self.NAMESPACES)
                if elements and elements[0].text:
                    date_text = elements[0].text.strip()
                    # Parse and normalize the date
                    try:
                        dt = datetime.strptime(date_text, "%Y-%m-%d")
                        return dt.strftime("%Y-%m-%d")
                    except ValueError:
                        continue
        
        # Method 2: Look in header/formData section
        for elem in root.iter():
            if 'period' in elem.tag.lower() and 'end' in elem.tag.lower():
                if elem.text:
                    try:
                        dt = datetime.strptime(elem.text.strip(), "%Y-%m-%d")
                        return dt.strftime("%Y-%m-%d")
                    except ValueError:
                        continue
        
        return None
    
    def _parse_holdings(
        self,
        root: ET.Element,
        fund_id: str,
        as_of_date: str,
        source_url: Optional[str],
    ) -> List[Holding]:
        """Parse holdings from the XML.
        
        Args:
            root: XML root element
            fund_id: Fund identifier
            as_of_date: Report date
            source_url: Source URL
            
        Returns:
            List of holdings
        """
        holdings = []
        
        # Try to find investment sections
        # N-PORT typically has <invstOrSec> tags within <invstOrSecs> or <investments>
        
        # Try multiple paths
        investment_paths = [
            './/ns1:invstOrSec',
            './/nport:invstOrSec',
            './/invstOrSec',
            './/ns1:investment',
            './/nport:investment',
            './/investment',
        ]
        
        investment_elements = []
        for path in investment_paths:
            elements = root.findall(path, self.NAMESPACES)
            if elements:
                investment_elements = elements
                break
        
        if not investment_elements:
            # Try without namespace
            for elem in root.iter():
                if 'invst' in elem.tag.lower() or 'security' in elem.tag.lower():
                    if self._has_holding_data(elem):
                        investment_elements.append(elem)
        
        print(f"Found {len(investment_elements)} investment elements")
        
        for inv_elem in investment_elements:
            holding = self._parse_single_holding(
                inv_elem,
                fund_id,
                as_of_date,
                source_url,
            )
            if holding:
                holdings.append(holding)
        
        return holdings
    
    def _has_holding_data(self, elem: ET.Element) -> bool:
        """Check if an element contains holding data.
        
        Args:
            elem: XML element
            
        Returns:
            True if element has holding-like children
        """
        # Look for typical holding fields
        text_content = ET.tostring(elem, encoding='unicode', method='text').lower()
        return any(keyword in text_content for keyword in ['cusip', 'isin', 'name', 'value'])
    
    def _parse_single_holding(
        self,
        elem: ET.Element,
        fund_id: str,
        as_of_date: str,
        source_url: Optional[str],
    ) -> Optional[Holding]:
        """Parse a single holding element.
        
        Args:
            elem: Investment XML element
            fund_id: Fund identifier
            as_of_date: Report date
            source_url: Source URL
            
        Returns:
            Holding object or None
        """
        # Extract fields using multiple strategies
        name = self._find_text(elem, ['name', 'issuerName', 'title', 'description'])
        if not name:
            return None
        
        cusip = self._find_text(elem, ['cusip', 'identifiers/cusip'])
        isin = self._find_text(elem, ['isin', 'identifiers/isin', 'otherIdentifier'])
        
        # Try to extract ISIN from identifier elements
        if not isin:
            for id_elem in elem.iter():
                if 'identifier' in id_elem.tag.lower():
                    id_type = self._find_text(id_elem, ['identifierType', 'type'])
                    if id_type and 'isin' in id_type.lower():
                        isin = self._find_text(id_elem, ['identifierValue', 'value'])
                        break
        
        balance_str = self._find_text(elem, ['balance', 'quantity', 'units', 'shares'])
        balance = self._parse_float(balance_str)
        
        value_str = self._find_text(elem, ['value', 'valUSD', 'marketValue', 'fairValue'])
        market_value = self._parse_float(value_str)
        
        currency = self._find_text(elem, ['currency', 'currencyCode', 'curCd']) or 'USD'
        
        category = self._find_text(elem, ['assetCategory', 'assetCat', 'category', 'instrumentType'])
        country = self._find_text(elem, ['country', 'countryCode', 'issuerCountry'])
        issuer = self._find_text(elem, ['issuerName', 'issuer'])
        
        # Check if derivative
        derivative_flag = False
        deriv_indicator = self._find_text(elem, ['derivativeInfo', 'derivative', 'isDerivative'])
        if deriv_indicator:
            derivative_flag = deriv_indicator.lower() in ('true', 'yes', '1')
        
        maturity = self._find_text(elem, ['maturityDate', 'maturity'])
        coupon_str = self._find_text(elem, ['couponRate', 'coupon', 'interestRate'])
        coupon = self._parse_float(coupon_str)
        
        return Holding(
            as_of=as_of_date,
            fund_id=fund_id,
            instrument_name_raw=name,
            cusip=cusip,
            isin=isin,
            balance=balance,
            market_value_local=market_value,
            currency=currency,
            category_raw=category,
            country_raw=country,
            derivative_flag=derivative_flag,
            issuer_name=issuer,
            maturity=maturity,
            coupon=coupon,
            source_url=source_url,
        )
    
    def _find_text(self, elem: ET.Element, paths: List[str]) -> Optional[str]:
        """Find text content in element using multiple path strategies.
        
        Args:
            elem: XML element
            paths: List of possible tag names/paths
            
        Returns:
            Text content or None
        """
        for path in paths:
            # Try with each namespace
            for ns_prefix in ['', 'ns1:', 'nport:']:
                full_path = f".//{ns_prefix}{path}"
                found = elem.find(full_path, self.NAMESPACES)
                if found is not None and found.text:
                    return found.text.strip()
                
                # Also try as direct child
                for child in elem:
                    tag_lower = child.tag.lower()
                    if path.lower() in tag_lower and child.text:
                        return child.text.strip()
        
        return None
    
    def _parse_float(self, value: Optional[str]) -> Optional[float]:
        """Parse a string to float.
        
        Args:
            value: String value
            
        Returns:
            Float value or None
        """
        if not value:
            return None
        try:
            return float(value.replace(',', ''))
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

