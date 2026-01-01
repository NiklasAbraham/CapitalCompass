"""BDIF document downloader for French UCITS reports."""

from __future__ import annotations

import hashlib
import json
import os
from urllib.parse import quote
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests


class BDIFDownloader:
    """Download BDIF PDF reports and store with metadata."""

    def __init__(self, raw_dir: Path):
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def download_report(
        self,
        pdf_url: str,
        isin: str,
        as_of_date: str,
        record_id: Optional[str] = None,
    ) -> Optional[Path]:
        """Download a BDIF report and save with metadata.

        Args:
            pdf_url: Direct PDF URL
            isin: ISIN code
            as_of_date: Report date (YYYY-MM-DD)
            record_id: BDIF record id

        Returns:
            Path to downloaded PDF or None
        """
        resolved_url = self._resolve_url(pdf_url)
        print(f"Downloading BDIF report from {resolved_url}")

        try:
            response = requests.get(
                resolved_url,
                timeout=60,
                headers={"User-Agent": "CapitalCompassBot/1.0"},
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"Download failed: {exc}")
            return None

        pdf_bytes = response.content
        sha256 = hashlib.sha256(pdf_bytes).hexdigest()

        doc_segment = f"doc_id={record_id}" if record_id else f"isin={isin}"
        output_dir = self.raw_dir / "bdif" / doc_segment
        output_dir.mkdir(parents=True, exist_ok=True)

        pdf_path = output_dir / f"{sha256}.pdf"
        if not pdf_path.exists():
            pdf_path.write_bytes(pdf_bytes)

        metadata = {
            "source_url": pdf_url,
            "discovered_at": datetime.utcnow().isoformat(),
            "as_of": as_of_date,
            "record_id": record_id,
            "sha256": sha256,
        }

        meta_path = output_dir / "metadata.json"
        with meta_path.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2)

        return pdf_path

    def _resolve_url(self, pdf_url: str) -> str:
        """Optionally route downloads through a relay proxy."""
        relay_base = os.environ.get("BDIF_ATTACHMENT_PROXY")
        if not relay_base:
            return pdf_url
        return f"{relay_base}{quote(pdf_url, safe='')}"
