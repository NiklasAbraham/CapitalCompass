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
    ) -> List[BDIFReportMetadata]:
        """Discover reports for a given ISIN.

        Args:
            isin: ISIN code (e.g., 'FR0011550185')
            target_date: Optional target date for backfill
            rows: Number of results to fetch

        Returns:
            List of report metadata sorted by as_of desc
        """
        print(f"Discovering BDIF reports for ISIN {isin}...")

        records: List[BDIFReportMetadata] = []

        for nature in ["A.1.1", "A.1.2"]:
            params = {
                "dataset": self.dataset,
                "q": isin,
                "facet": "document_type",
                "sort": "-publication_date",
                "rows": rows,
            }

            payload = self._get_json(params)
            if not payload:
                continue

            for record in payload.get("records", []):
                fields = record.get("fields", {})
                document_type = fields.get("document_type", "")
                if not document_type.startswith(nature):
                    continue
                url = fields.get("attachment_original")
                if not url:
                    continue

                as_of = self._parse_date(fields.get("date_cloture"))
                if not as_of:
                    as_of = self._parse_date(fields.get("publication_date"))
                if not as_of:
                    continue

                if target_date and as_of != target_date:
                    continue

                record_id = fields.get("doc_id") or record.get("recordid", "")
                title = fields.get("title") or fields.get("titre") or fields.get("libelle")

                records.append(
                    BDIFReportMetadata(
                        pdf_url=url,
                        as_of=as_of,
                        record_id=record_id,
                        nature_document=document_type,
                        title=title,
                    )
                )

        records.sort(key=lambda r: r.as_of, reverse=True)

        print(f"Found {len(records)} report(s)")
        for report in records:
            print(f"  {report.as_of} | {report.nature_document} | {report.pdf_url}")

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
        """Parse YYYY-MM-DD date string."""
        if not value:
            return None
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
