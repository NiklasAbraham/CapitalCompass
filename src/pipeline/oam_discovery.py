"""OAM (Officially Appointed Mechanism) discovery module.

Discovers holdings reports from Luxembourg LuxSE OAM and German Bundesanzeiger
for UCITS ETFs.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Iterator
import requests
from bs4 import BeautifulSoup

try:
    from deutschland.bundesanzeiger import Bundesanzeiger
except ImportError:
    Bundesanzeiger = None


@dataclass
class OAMReportMetadata:
    """Metadata for a discovered OAM report."""
    
    pdf_url: str
    as_of: date
    title: str
    jurisdiction: str  # 'LU' or 'DE'
    report_type: str  # 'annual' or 'half-yearly'


class OAMDiscovery:
    """Discover holdings reports from European OAM sources."""
    
    LUXSE_BASE_URL = "https://www.bourse.lu"
    LUXSE_SEARCH_URL = f"{LUXSE_BASE_URL}/oam-search"
    REQUEST_DELAY = 0.5  # 500ms between requests
    
    def __init__(self):
        """Initialize discovery client."""
        self._last_request_time = 0.0
        self._bundesanzeiger = None
    
    def discover_reports(
        self,
        isin: str,
        jurisdiction: str,
        target_date: Optional[date] = None,
    ) -> List[OAMReportMetadata]:
        """Discover reports for a given ISIN.
        
        Args:
            isin: ISIN code (e.g., 'LU0908500753')
            jurisdiction: 'LU' for Luxembourg, 'DE' for Germany
            target_date: Optional target date for backfill
            
        Returns:
            List of report metadata
        """
        if jurisdiction == 'LU':
            return list(self._discover_lu_oam(isin, target_date))
        elif jurisdiction == 'DE':
            return list(self._discover_de_fondsdata(isin, target_date))
        else:
            raise ValueError(f"Unsupported jurisdiction: {jurisdiction}")
    
    def _discover_lu_oam(
        self,
        isin: str,
        target_date: Optional[date] = None,
    ) -> Iterator[OAMReportMetadata]:
        """Discover reports from Luxembourg LuxSE OAM.
        
        Args:
            isin: ISIN code
            target_date: Optional target date
            
        Yields:
            Report metadata
        """
        print(f"Discovering LuxSE OAM reports for ISIN {isin}...")
        
        # Build form payload
        payload = {
            "countryOfIssuer": "",
            "issuerName": "",
            "isinCode": isin,
            "referenceYear": str(target_date.year) if target_date else "",
            "informationType": "Periodic information",
        }
        
        self._throttle()
        
        try:
            response = requests.post(
                self.LUXSE_SEARCH_URL,
                data=payload,
                timeout=30,
                headers={
                    "User-Agent": "CapitalCompassBot/1.0",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error fetching LuxSE search results: {e}")
            return
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Find table rows with reports
        rows = soup.select("table tbody tr")
        if not rows:
            # Try alternative selectors
            rows = soup.select("tr")
        
        found_reports = []
        
        for row in rows:
            try:
                # Look for title/link in the row
                title_elem = row.select_one("td.title, td:first-child, a")
                if not title_elem:
                    continue
                
                title_text = title_elem.get_text(strip=True)
                
                # Check if it's a financial report
                title_lower = title_text.lower()
                if not any(
                    keyword in title_lower
                    for keyword in ["financial report", "annual", "half-yearly", "semiannual"]
                ):
                    continue
                
                # Extract link
                link_elem = row.select_one("a[href]")
                if not link_elem:
                    continue
                
                href = link_elem.get("href", "")
                if not href:
                    continue
                
                # Build full URL
                if href.startswith("/"):
                    pdf_url = f"{self.LUXSE_BASE_URL}{href}"
                elif href.startswith("http"):
                    pdf_url = href
                else:
                    pdf_url = f"{self.LUXSE_BASE_URL}/{href}"
                
                # Extract date from title or row
                as_of_date = self._extract_date_from_title(title_text, target_date)
                if not as_of_date:
                    # Try to extract from other cells
                    date_cells = row.select("td")
                    for cell in date_cells:
                        as_of_date = self._extract_date_from_text(cell.get_text())
                        if as_of_date:
                            break
                
                if not as_of_date:
                    print(f"Warning: Could not extract date from '{title_text}', skipping")
                    continue
                
                # Determine report type
                report_type = "annual" if "annual" in title_lower else "half-yearly"
                
                found_reports.append(
                    OAMReportMetadata(
                        pdf_url=pdf_url,
                        as_of=as_of_date,
                        title=title_text,
                        jurisdiction="LU",
                        report_type=report_type,
                    )
                )
            except Exception as e:
                print(f"Error parsing row: {e}")
                continue
        
        # Sort by date descending
        found_reports.sort(key=lambda r: r.as_of, reverse=True)
        
        print(f"Found {len(found_reports)} report(s)")
        for report in found_reports:
            print(f"  {report.as_of}: {report.title}")
        
        yield from found_reports
    
    def _discover_de_fondsdata(
        self,
        isin: str,
        target_date: Optional[date] = None,
    ) -> Iterator[OAMReportMetadata]:
        """Discover reports from German Bundesanzeiger Fondsdata.
        
        Args:
            isin: ISIN code
            target_date: Optional target date
            
        Yields:
            Report metadata
        """
        print(f"Discovering Bundesanzeiger reports for ISIN {isin}...")
        
        if Bundesanzeiger is None:
            print("Error: deutschland package not installed")
            print("Install with: pip install deutschland")
            return
        
        if self._bundesanzeiger is None:
            self._bundesanzeiger = Bundesanzeiger()
        
        try:
            meta = self._bundesanzeiger.get_reports(isin)
        except Exception as e:
            print(f"Error fetching Bundesanzeiger reports: {e}")
            return
        
        if not meta or "reports" not in meta:
            print(f"No reports found for ISIN {isin}")
            return
        
        found_reports = []
        
        for rep in meta["reports"]:
            title = rep.get("title", "")
            title_lower = title.lower()
            
            # Check if it's a financial report
            if not any(
                keyword in title_lower
                for keyword in ["jahresbericht", "halbjahresbericht", "annual", "half-yearly"]
            ):
                continue
            
            download_url = rep.get("downloadUrl")
            if not download_url:
                continue
            
            # Extract date from title
            as_of_date = self._extract_date_from_title(title, target_date)
            if not as_of_date:
                # Try to parse from other fields
                date_str = rep.get("date") or rep.get("publicationDate")
                if date_str:
                    as_of_date = self._extract_date_from_text(date_str)
            
            if not as_of_date:
                print(f"Warning: Could not extract date from '{title}', skipping")
                continue
            
            # Determine report type
            report_type = "annual" if "jahresbericht" in title_lower or "annual" in title_lower else "half-yearly"
            
            found_reports.append(
                OAMReportMetadata(
                    pdf_url=download_url,
                    as_of=as_of_date,
                    title=title,
                    jurisdiction="DE",
                    report_type=report_type,
                )
            )
        
        # Sort by date descending
        found_reports.sort(key=lambda r: r.as_of, reverse=True)
        
        print(f"Found {len(found_reports)} report(s)")
        for report in found_reports:
            print(f"  {report.as_of}: {report.title}")
        
        yield from found_reports
    
    def _extract_date_from_title(self, title: str, target_date: Optional[date] = None) -> Optional[date]:
        """Extract date from report title.
        
        Args:
            title: Report title
            target_date: Optional target date for validation
            
        Returns:
            Extracted date or None
        """
        # Try various date patterns
        patterns = [
            r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
            r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})",  # DD.MM.YYYY
            r"(\d{4})-(\d{1,2})-(\d{1,2})",  # YYYY-MM-DD
            r"(\d{1,2})/(\d{1,2})/(\d{4})",  # MM/DD/YYYY or DD/MM/YYYY
            r"(\d{4})",  # Just year
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                try:
                    if len(match.groups()) == 3:
                        if pattern.startswith(r"(\d{1,2})\s+"):
                            # Month name format
                            day, month_name, year = match.groups()
                            month_map = {
                                "january": 1, "february": 2, "march": 3, "april": 4,
                                "may": 5, "june": 6, "july": 7, "august": 8,
                                "september": 9, "october": 10, "november": 11, "december": 12,
                            }
                            month = month_map.get(month_name.lower())
                            if month:
                                return date(int(year), month, int(day))
                        elif "." in pattern:
                            # DD.MM.YYYY format
                            day, month, year = match.groups()
                            return date(int(year), int(month), int(day))
                        elif "-" in pattern:
                            # YYYY-MM-DD format
                            year, month, day = match.groups()
                            return date(int(year), int(month), int(day))
                        else:
                            # MM/DD/YYYY or DD/MM/YYYY - try both
                            part1, part2, year = match.groups()
                            try:
                                return date(int(year), int(part1), int(part2))
                            except ValueError:
                                return date(int(year), int(part2), int(part1))
                    elif len(match.groups()) == 1:
                        # Just year
                        year = int(match.group(1))
                        if target_date:
                            # Use target date's month/day with extracted year
                            return date(year, target_date.month, target_date.day)
                        else:
                            # Default to end of year
                            return date(year, 12, 31)
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _extract_date_from_text(self, text: str) -> Optional[date]:
        """Extract date from arbitrary text.
        
        Args:
            text: Text to parse
            
        Returns:
            Extracted date or None
        """
        return self._extract_date_from_title(text)
    
    def _throttle(self):
        """Ensure polite rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()
