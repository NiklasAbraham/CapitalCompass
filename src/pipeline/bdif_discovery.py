"""BDIF (AMF) discovery module for French UCITS reports.

Uses the info-financiere.gouv.fr Opendatasoft API to discover
annual and semi-annual financial reports for French-domiciled ETFs.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

import requests


@dataclass
class BDIFReportMetadata:
    """Metadata for a discovered BDIF report."""

    pdf_url: str
    as_of: date
    record_id: str
    nature_document: str
    title: Optional[str] = None


class BDIFDiscovery:
    """Discover BDIF holdings reports for French UCITS funds."""

    DEFAULT_BASE_URL = "https://info-financiere.gouv.fr/api/records/1.0/search/"
    REQUEST_DELAY = 1.0
    MAX_RETRIES = 3
    BACKOFF_SECONDS = 2.0

    def __init__(
        self,
        dataset: str = "flux-amf-new-prod",
        base_url: Optional[str] = None,
    ):
        self.dataset = dataset
        self.base_url = base_url or os.environ.get("BDIF_BASE_URL", self.DEFAULT_BASE_URL)
        self._last_request_time = 0.0

    def discover_reports(
        self,
        isin: str,
        target_date: Optional[date] = None,
        rows: int = 100,
        debug: bool = False,
    ) -> List[BDIFReportMetadata]:
        """Discover reports for a given ISIN.

        Args:
            isin: ISIN code (e.g., 'FR0011550185')
            target_date: Optional target date for backfill
            rows: Number of results to fetch
            debug: Enable debug logging

        Returns:
            List of report metadata sorted by as_of desc
        """
        print(f"Discovering BDIF reports for ISIN {isin}...")

        records: List[BDIFReportMetadata] = []

        # Search by ISIN - try multiple search strategies
        # Note: The info-financiere.gouv.fr API appears to be primarily for listed companies,
        # not UCITS funds. BDIF reports for UCITS may need to be accessed through the
        # BDIF website directly (https://bdif.amf-france.org) or a different API endpoint.
        search_queries = [
            (isin, "Direct ISIN search"),
            (f"identificationsociete_iso_cd_isi:{isin}", "Field-specific ISIN search"),
            (f'code_isin_nom_sc:"*{isin}*"', "ISIN in code_isin_nom_sc field"),
            # Also try searching by partial ISIN in case of formatting differences
            (isin[:9], "Partial ISIN search (first 9 chars)"),
        ]

        for query, query_desc in search_queries:
            if debug:
                print(f"  Trying: {query_desc} ({query})")
            
            params = {
                "dataset": self.dataset,
                "q": query,
                "rows": rows,
            }

            payload = self._get_json(params)
            if not payload:
                if debug:
                    print(f"    No payload returned")
                continue

            total_hits = payload.get("nhits", 0)
            if debug:
                print(f"    API returned {total_hits} total hits, {len(payload.get('records', []))} records in response")

            for record in payload.get("records", []):
                fields = record.get("fields", {})
                
                # Debug: show what we found
                if debug:
                    record_isin = fields.get("identificationsociete_iso_cd_isi", "N/A")
                    record_title = fields.get("informationdeposee_inf_tit_inf", "N/A")[:60]
                    print(f"    Record: ISIN={record_isin}, Title={record_title}")
                
                # Verify this record matches our ISIN
                record_isin = fields.get("identificationsociete_iso_cd_isi", "")
                if record_isin != isin:
                    if debug:
                        print(f"      Skipping: ISIN mismatch ({record_isin} != {isin})")
                    continue
                
                # Get PDF URL - use url_de_recuperation field
                url = fields.get("url_de_recuperation")
                if not url:
                    if debug:
                        print(f"      Skipping: No PDF URL found")
                    continue

                # Get date - try multiple date fields
                as_of = self._parse_date(fields.get("uin_dat_amf"))
                if not as_of:
                    as_of = self._parse_date(fields.get("uin_dat_mar"))
                if not as_of:
                    as_of = self._parse_date(fields.get("informationdeposee_inf_dat_emt"))
                if not as_of:
                    if debug:
                        print(f"      Skipping: No valid date found")
                    continue

                if target_date and as_of != target_date:
                    if debug:
                        print(f"      Skipping: Date mismatch ({as_of} != {target_date})")
                    continue

                # Get document type information
                doc_code = fields.get("informationdeposee_inf_cod_dif", "")
                doc_subtype = fields.get("sous_type_d_information", "")
                doc_type = fields.get("type_d_information", "")
                
                if debug:
                    print(f"      Document info: code={doc_code}, subtype={doc_subtype[:40]}, type={doc_type[:40]}")
                
                # Filter for BDIF reports - look for periodic financial reports
                # Accept reports that might contain holdings information
                is_periodic_report = (
                    "périodique" in doc_type.lower() or
                    "periodic" in doc_type.lower() or
                    "rapport" in doc_subtype.lower() or
                    "report" in doc_subtype.lower() or
                    "composition" in doc_subtype.lower() or
                    "actif" in doc_subtype.lower() or
                    "portefeuille" in doc_subtype.lower() or
                    "portfolio" in doc_subtype.lower()
                )
                
                # Accept all reports with PDFs for now - let parser filter
                # This is more permissive but ensures we don't miss valid reports
                if debug and not is_periodic_report:
                    print(f"      Note: Not clearly a periodic report, but including anyway")

                record_id = record.get("recordid", "")
                title = fields.get("informationdeposee_inf_tit_inf") or fields.get("code_isin_nom_sc", "")

                if debug:
                    print(f"      ✓ Adding report: {as_of} | {title[:50]}")

                records.append(
                    BDIFReportMetadata(
                        pdf_url=url,
                        as_of=as_of,
                        record_id=record_id,
                        nature_document=doc_code or doc_subtype or doc_type,
                        title=title,
                    )
                )
            
            # If we found records with this query, don't try the next one
            if records:
                if debug:
                    print(f"  Found {len(records)} records with {query_desc}, stopping search")
                break

        records.sort(key=lambda r: r.as_of, reverse=True)

        print(f"Found {len(records)} report(s)")
        for report in records:
            print(f"  {report.as_of} | {report.nature_document[:40]} | {report.title[:50] if report.title else 'N/A'}")

        return records

    def _get_json(self, params: dict) -> Optional[dict]:
        """GET JSON with retry + throttle."""
        self._throttle()

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = requests.get(
                    self.base_url,
                    params=params,
                    timeout=30,
                    headers={
                        "User-Agent": "CapitalCompassBot/1.0",
                        "Accept": "application/json",
                    },
                )
                if response.status_code >= 500:
                    raise requests.RequestException(
                        f"Server error {response.status_code}"
                    )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                if attempt >= self.MAX_RETRIES:
                    print(f"Error fetching BDIF data: {exc}")
                    return None
                sleep_for = self.BACKOFF_SECONDS * attempt
                print(f"Retrying BDIF request in {sleep_for:.1f}s (attempt {attempt})")
                time.sleep(sleep_for)
        return None

    def _throttle(self) -> None:
        """Throttle requests to respect rate limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        """Parse date from various formats (YYYY-MM-DD or ISO datetime)."""
        if not value:
            return None
        try:
            # Try ISO datetime format first (e.g., "2012-04-12T16:30:31+00:00")
            if "T" in value:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            # Try simple date format
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            return None
