"""SEC Form N-PORT discovery module.

Discovers N-PORT filings from the SEC EDGAR system for registered investment companies.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List
import requests


@dataclass
class FilingMetadata:
    """Metadata for a discovered N-PORT filing."""
    
    cik: str
    accession: str
    filing_date: datetime
    as_of_date: datetime
    primary_doc_url: str
    series_id: Optional[str] = None
    class_id: Optional[str] = None


class NPORTDiscovery:
    """Discover N-PORT filings from SEC EDGAR."""
    
    SEC_EDGAR_BASE = "https://www.sec.gov"
    SEC_DATA_BASE = "https://data.sec.gov"
    USER_AGENT = "CapitalCompass/1.0 (research tool; contact@example.com)"
    REQUEST_DELAY = 0.15  # 150ms between requests (polite rate limit)
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize discovery client.
        
        Args:
            cache_dir: Directory to cache discovery results
        """
        self.cache_dir = cache_dir
        self._last_request_time = 0.0
        
    def discover_filings(
        self,
        cik: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        series_id: Optional[str] = None,
        class_id: Optional[str] = None,
    ) -> List[FilingMetadata]:
        """Discover N-PORT filings for a given CIK.
        
        Args:
            cik: Central Index Key (10-digit padded)
            from_date: Start date for filing search
            to_date: End date for filing search
            series_id: Optional series ID filter
            class_id: Optional class ID filter
            
        Returns:
            List of filing metadata
        """
        # Normalize CIK to 10 digits
        cik_padded = cik.zfill(10)
        
        # Build the submissions URL
        submissions_url = f"{self.SEC_DATA_BASE}/submissions/CIK{cik_padded}.json"
        
        print(f"Discovering N-PORT filings for CIK {cik_padded}...")
        submissions_data = self._fetch_json(submissions_url)
        
        if not submissions_data:
            print(f"No submission data found for CIK {cik_padded}")
            return []
        
        # Extract recent filings
        filings = submissions_data.get("filings", {}).get("recent", {})
        if not filings:
            print(f"No recent filings found for CIK {cik_padded}")
            return []
        
        # Filter for N-PORT forms
        results = []
        forms = filings.get("form", [])
        accessions = filings.get("accessionNumber", [])
        filing_dates = filings.get("filingDate", [])
        primary_docs = filings.get("primaryDocument", [])
        
        for i, form in enumerate(forms):
            if form not in ("NPORT-P", "NPORT-EX"):
                continue
            
            accession = accessions[i] if i < len(accessions) else None
            filing_date_str = filing_dates[i] if i < len(filing_dates) else None
            primary_doc = primary_docs[i] if i < len(primary_docs) else None
            
            if not all([accession, filing_date_str, primary_doc]):
                continue
            
            filing_date = datetime.strptime(filing_date_str, "%Y-%m-%d")
            
            # Apply date filters
            if from_date and filing_date.date() < from_date:
                continue
            if to_date and filing_date.date() > to_date:
                continue
            
            # Build document URL - need to get the actual XML file, not the rendered HTML
            # The actual NPORT data is typically in a file like NPORT-P_xxxxx.xml
            accession_no_dash = accession.replace("-", "")
            
            # First, try to get the filing index to find the XML file
            filing_url = f"{self.SEC_EDGAR_BASE}/cgi-bin/viewer?action=view&cik={cik_padded}&accession_number={accession}&xbrl_type=v"
            
            # For now, construct the likely XML filename
            # N-PORT XML files are usually named like "nport-p_*.xml" or similar
            # We'll try the primary doc first, but ideally we'd fetch the index
            doc_url = f"{self.SEC_EDGAR_BASE}/Archives/edgar/data/{cik_padded}/{accession_no_dash}/{primary_doc}"
            
            # Alternative: try to find the actual XML instance document
            # This would require fetching the filing's index.json or listing
            xml_doc_url = self._find_nport_xml_url(cik_padded, accession_no_dash, primary_doc)
            
            # For N-PORT, the as_of date is typically the last day of the month
            # We'll extract this from the filing itself later
            as_of_date = filing_date  # Placeholder, will be refined during parsing
            
            # Use the XML URL if we found it, otherwise fall back to primary doc
            final_url = xml_doc_url if xml_doc_url else doc_url
            
            results.append(
                FilingMetadata(
                    cik=cik_padded,
                    accession=accession,
                    filing_date=filing_date,
                    as_of_date=as_of_date,
                    primary_doc_url=final_url,
                    series_id=series_id,
                    class_id=class_id,
                )
            )
        
        print(f"Found {len(results)} N-PORT filing(s)")
        return results
    
    def _fetch_json(self, url: str) -> Optional[dict]:
        """Fetch JSON from SEC with rate limiting.
        
        Args:
            url: URL to fetch
            
        Returns:
            Parsed JSON data or None on error
        """
        self._throttle()
        
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json",
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def _find_nport_xml_url(self, cik: str, accession_no_dash: str, primary_doc: str) -> Optional[str]:
        """Find the actual XML instance document URL.
        
        Args:
            cik: CIK (10-digit padded)
            accession_no_dash: Accession number without dashes
            primary_doc: Primary document filename
            
        Returns:
            URL to XML file or None
        """
        # Fetch the filing's index.json to get all documents
        index_url = f"{self.SEC_EDGAR_BASE}/cgi-bin/viewer?action=view&cik={cik}&accession_number={accession_no_dash.replace('-', '')}&xbrl_type=v&count=40"
        
        # Try to fetch filing index directly
        filing_dir = f"{self.SEC_EDGAR_BASE}/Archives/edgar/data/{cik}/{accession_no_dash}"
        
        try:
            # Fetch the directory listing as HTML and parse for XML files
            self._throttle()
            headers = {"User-Agent": self.USER_AGENT}
            response = requests.get(filing_dir, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # Look for XML files in the HTML response
                content = response.text.lower()
                
                # Common N-PORT XML file patterns
                xml_patterns = [
                    'nport-p.xml',
                    'nport_p.xml',
                    'nport-ex.xml',
                    'nport_ex.xml',
                ]
                
                for pattern in xml_patterns:
                    if pattern in content:
                        # Extract the actual filename (case-sensitive)
                        match = re.search(rf'href="([^"]*{pattern}[^"]*)"', response.text, re.IGNORECASE)
                        if match:
                            filename = match.group(1)
                            return f"{filing_dir}/{filename}"
                
                # If no match, look for any .xml file that's not primary_doc.xml
                xml_matches = re.findall(r'href="([^"]*\.xml)"', response.text, re.IGNORECASE)
                for match in xml_matches:
                    if 'primary_doc' not in match.lower() and 'xsl' not in match.lower():
                        return f"{filing_dir}/{match}"
        
        except Exception as e:
            print(f"Error finding XML URL: {e}")
        
        return None
    
    def _throttle(self):
        """Ensure polite rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

