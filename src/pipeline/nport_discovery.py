"""SEC Form N-PORT discovery module.

Discovers N-PORT filings from the SEC EDGAR system for registered investment companies.
"""

from __future__ import annotations

import json
import re
import time
import os
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Tuple
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
    DEFAULT_USER_AGENT = (
        "CapitalCompassBot/1.0 (gpt-5-codex; support@capitalcompass.ai)"
    )
    USER_AGENT = os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)
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
        # Normalize CIK to 10 digits for API usage but also keep the
        # non-padded representation for file-system URLs.
        cik_padded = cik.zfill(10)
        cik_no_padding = self._strip_cik_padding(cik_padded)
        
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
        report_dates = filings.get("reportDate", [])
        period_of_report = filings.get("periodOfReport", [])
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
            as_of_source = None
            if i < len(report_dates) and report_dates[i]:
                as_of_source = report_dates[i]
            elif i < len(period_of_report) and period_of_report[i]:
                as_of_source = period_of_report[i]
            if as_of_source:
                try:
                    as_of_date = datetime.strptime(as_of_source, "%Y-%m-%d")
                except ValueError:
                    as_of_date = filing_date
            else:
                as_of_date = filing_date
            
            # Apply date filters
            if from_date and filing_date.date() < from_date:
                continue
            if to_date and filing_date.date() > to_date:
                continue
            
            # Build document URL - need to get the actual XML file, not the rendered HTML
            # The actual NPORT data is typically in a file like NPORT-P_xxxxx.xml
            accession_no_dash = accession.replace("-", "")

            # First, try to get the filing index to find the XML file
            filing_url = (
                f"{self.SEC_EDGAR_BASE}/cgi-bin/viewer?action=view&cik={cik_padded}"
                f"&accession_number={accession}&xbrl_type=v"
            )

            # Construct likely locations for the primary document. EDGAR stores
            # filings both with dashed and non-dashed accession folders, so we
            # try both variants when building URLs.
            candidate_dirs = self._candidate_filing_directories(
                cik_no_padding, accession
            )
            doc_url = None
            if candidate_dirs:
                doc_url = f"{candidate_dirs[0][1]}/{primary_doc}"
            if not doc_url:
                # Fall back to the legacy path that used the non-dashed accession
                # folder. This is kept for compatibility even though the dashed
                # folder is canonical.
                doc_url = (
                    f"{self.SEC_EDGAR_BASE}/Archives/edgar/data/{cik_no_padding}/"
                    f"{accession_no_dash}/{primary_doc}"
                )

            # Alternative: try to find the actual XML instance document by
            # inspecting the filing directory manifests.
            xml_doc_url = self._find_nport_xml_url(
                cik_no_padding, accession, primary_doc, candidate_dirs
            )
            
            # For N-PORT, the as_of date is typically the last day of the month
            # We'll extract this from the filing itself later
            # Use the XML URL if we found it, otherwise fall back to primary doc
            final_url = xml_doc_url if xml_doc_url else doc_url or filing_url

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

        # Sort results by filing date ascending to keep chronological order
        results.sort(key=lambda f: f.filing_date)

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
    
    def _candidate_filing_directories(self, cik_no_padding: str, accession: str) -> List[Tuple[str, str]]:
        """Return potential EDGAR directory URLs for a filing.

        Args:
            cik_no_padding: CIK without leading zero padding.
            accession: Accession number with dashes.

        Returns:
            List of tuples mapping accession folder name to full base URL.
        """

        accession_variants: List[str] = []
        if accession:
            accession_variants.append(accession)
            accession_variants.append(accession.replace("-", ""))

        seen = set()
        directories: List[Tuple[str, str]] = []
        for variant in accession_variants:
            if not variant or variant in seen:
                continue
            seen.add(variant)
            base_url = f"{self.SEC_EDGAR_BASE}/Archives/edgar/data/{cik_no_padding}/{variant}"
            directories.append((variant, base_url))

        return directories

    def _find_nport_xml_url(
        self,
        cik_no_padding: str,
        accession: str,
        primary_doc: str,
        candidate_dirs: Optional[List[Tuple[str, str]]] = None,
    ) -> Optional[str]:
        """Find the actual XML instance document URL.

        Args:
            cik_no_padding: CIK without leading zero padding
            accession: Accession number with dashes
            primary_doc: Primary document filename

        Returns:
            URL to XML file or None
        """
        candidate_dirs = candidate_dirs or self._candidate_filing_directories(
            cik_no_padding, accession
        )

        if not candidate_dirs:
            return None

        # Try structured index.json files first because they list every asset in
        # a filing directory with reliable metadata.
        for accession_folder, base_url in candidate_dirs:
            index_url = f"{base_url}/index.json"
            index_json = self._fetch_json(index_url)
            if not index_json:
                continue

            directory = index_json.get("directory", {})
            items = directory.get("item", [])
            if isinstance(items, dict):
                items = [items]

            ranked_candidates: list[tuple[int, str]] = []

            for item in items:
                name = (item.get("name") or "").strip()
                href = (item.get("href") or name).strip()
                if not name:
                    continue

                href_lower = href.lower()
                if not href_lower.endswith(".xml"):
                    continue

                if "primary_doc" in href_lower or href_lower.endswith(".xsl.xml"):
                    continue

                content_type = (item.get("type") or "").lower()
                size_hint = int(item.get("size", 0) or 0)
                seq = int(item.get("seq", 0) or 0)

                score = 0
                if "xml" in content_type:
                    score += 5
                if re.search(r"nport[-_]?p", href_lower):
                    score += 100
                if re.search(r"nport[-_]?ex", href_lower):
                    score += 80
                if "instance" in href_lower:
                    score += 40
                if href_lower.endswith(".xml"):
                    score += 10
                if size_hint > 0:
                    score += min(size_hint // 10000, 20)
                if seq > 0:
                    score += min(seq, 10)

                # Deprioritise filing summary and submission metadata files
                if "summary" in href_lower or "submission" in href_lower:
                    score -= 25

                if score < 0:
                    continue

                url = f"{base_url}/{href.lstrip('./')}"
                ranked_candidates.append((score, url))

            if ranked_candidates:
                ranked_candidates.sort(key=lambda item: item[0], reverse=True)
                return ranked_candidates[0][1]

        # As a fallback, scrape the HTML directory listing for XML files.
        headers = {"User-Agent": self.USER_AGENT}
        for accession_folder, base_url in candidate_dirs:
            try:
                self._throttle()
                response = requests.get(base_url + "/", headers=headers, timeout=10)
            except requests.RequestException as exc:
                print(f"Error fetching directory listing for {base_url}: {exc}")
                continue

            if response.status_code != 200:
                continue

            content = response.text
            content_lower = content.lower()

            xml_patterns = [
                "nport-p.xml",
                "nport_p.xml",
                "nport-ex.xml",
                "nport_ex.xml",
            ]

            for pattern in xml_patterns:
                if pattern in content_lower:
                    match = re.search(
                        rf'href="([^"]*{pattern}[^"]*)"', content, re.IGNORECASE
                    )
                    if match:
                        filename = match.group(1).lstrip("./")
                        return f"{base_url}/{filename}"

            xml_matches = re.findall(r'href="([^"]*\.xml)"', content, re.IGNORECASE)
            for match in xml_matches:
                lowered = match.lower()
                if "primary_doc" in lowered or "xsl" in lowered:
                    continue
                filename = match.lstrip("./")
                return f"{base_url}/{filename}"

        return None

    @staticmethod
    def _strip_cik_padding(cik: str) -> str:
        """Return the non-padded representation of a CIK string."""

        if not cik:
            return cik

        try:
            return str(int(cik))
        except (TypeError, ValueError):
            return cik.lstrip("0") or "0"
    
    def _throttle(self):
        """Ensure polite rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

