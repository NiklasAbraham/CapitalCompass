"""OAM PDF download module with throttling and retry logic."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional
import requests


class OAMDownloader:
    """Download PDF reports from OAM sources."""
    
    REQUEST_DELAY = 0.5  # 500ms between requests
    MAX_RETRIES = 3
    RETRY_BACKOFF = 2.0  # Exponential backoff multiplier
    
    def __init__(self, raw_data_dir: Path):
        """Initialize downloader.
        
        Args:
            raw_data_dir: Base directory for raw data storage
        """
        self.raw_data_dir = raw_data_dir
        self._last_request_time = 0.0
    
    def download_report(
        self,
        pdf_url: str,
        isin: str,
        as_of_date: str,
        jurisdiction: str,
    ) -> Optional[Path]:
        """Download a PDF report and store it with metadata.
        
        Args:
            pdf_url: URL of the PDF report
            isin: ISIN of the fund
            as_of_date: Report date (YYYY-MM-DD)
            jurisdiction: 'LU' or 'DE'
            
        Returns:
            Path to the downloaded file, or None on failure
        """
        print(f"Downloading PDF from {pdf_url}...")
        
        # Download with retry logic
        pdf_bytes = self._download_with_retry(pdf_url)
        if pdf_bytes is None:
            return None
        
        # Compute SHA256 hash
        sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()
        
        # Create storage path
        storage_path = self._build_storage_path(isin, as_of_date, sha256_hash, jurisdiction)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write PDF file
        pdf_path = storage_path.parent / f"{sha256_hash}.pdf"
        pdf_path.write_bytes(pdf_bytes)
        
        # Write metadata
        metadata = {
            "source_url": pdf_url,
            "isin": isin,
            "as_of": as_of_date,
            "sha256": sha256_hash,
            "jurisdiction": jurisdiction,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "size_bytes": len(pdf_bytes),
        }
        
        metadata_path = storage_path.parent / "metadata.json"
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        
        print(f"Saved to {pdf_path}")
        print(f"SHA256: {sha256_hash}")
        
        return pdf_path
    
    def _download_with_retry(self, url: str) -> Optional[bytes]:
        """Download with exponential backoff retry.
        
        Args:
            url: URL to download
            
        Returns:
            Downloaded bytes or None on failure
        """
        headers = {
            "User-Agent": "CapitalCompassBot/1.0",
            "Accept": "application/pdf,*/*",
        }
        
        for attempt in range(self.MAX_RETRIES):
            self._throttle()
            
            try:
                response = requests.get(url, headers=headers, timeout=60)
                response.raise_for_status()
                
                # Verify it's actually a PDF
                content_type = response.headers.get("Content-Type", "").lower()
                if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                    # Check first bytes for PDF magic number
                    if not response.content[:4] == b"%PDF":
                        print(f"Warning: Response may not be a PDF (Content-Type: {content_type})")
                
                return response.content
            except requests.RequestException as e:
                print(f"Download attempt {attempt + 1}/{self.MAX_RETRIES} failed: {e}")
                
                if attempt < self.MAX_RETRIES - 1:
                    backoff = self.RETRY_BACKOFF ** attempt
                    print(f"Retrying in {backoff:.1f}s...")
                    time.sleep(backoff)
        
        print(f"Failed to download {url} after {self.MAX_RETRIES} attempts")
        return None
    
    def _build_storage_path(
        self,
        isin: str,
        as_of_date: str,
        sha256_hash: str,
        jurisdiction: str,
    ) -> Path:
        """Build the storage path for a report.
        
        Args:
            isin: ISIN
            as_of_date: Report date
            sha256_hash: File hash
            jurisdiction: 'LU' or 'DE'
            
        Returns:
            Path to metadata file location
        """
        # Structure: raw/oam_{jurisdiction}/isin={ISIN}/as_of={DATE}/
        path = (
            self.raw_data_dir
            / f"oam_{jurisdiction.lower()}"
            / f"isin={isin}"
            / f"as_of={as_of_date}"
        )
        return path / "metadata.json"
    
    def _throttle(self):
        """Ensure polite rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()
