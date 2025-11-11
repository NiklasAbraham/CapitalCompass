"""SEC Form N-PORT download module with throttling and retry logic."""

from __future__ import annotations

import hashlib
import json
import time
import os
from pathlib import Path
from typing import Optional
import requests


class NPORTDownloader:
    """Download N-PORT XML files from SEC EDGAR."""
    
    DEFAULT_USER_AGENT = (
        "CapitalCompassBot/1.0 (gpt-5-codex; support@capitalcompass.ai)"
    )
    USER_AGENT = os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)
    REQUEST_DELAY = 0.15  # 150ms between requests
    MAX_RETRIES = 3
    RETRY_BACKOFF = 2.0  # Exponential backoff multiplier
    
    def __init__(self, raw_data_dir: Path):
        """Initialize downloader.
        
        Args:
            raw_data_dir: Base directory for raw data storage
        """
        self.raw_data_dir = raw_data_dir
        self._last_request_time = 0.0
    
    def download_filing(
        self,
        url: str,
        cik: str,
        accession: str,
        as_of_date: str,
    ) -> Optional[Path]:
        """Download a filing and store it with metadata.
        
        Args:
            url: URL of the XML filing
            cik: CIK of the fund
            accession: SEC accession number
            as_of_date: Report date (YYYY-MM-DD)
            
        Returns:
            Path to the downloaded file, or None on failure
        """
        print(f"Downloading filing from {url}...")
        
        # Download with retry logic
        xml_bytes = self._download_with_retry(url)
        if xml_bytes is None:
            return None
        
        # Compute SHA256 hash
        sha256_hash = hashlib.sha256(xml_bytes).hexdigest()
        
        # Create storage path
        storage_path = self._build_storage_path(cik, accession, as_of_date, sha256_hash)
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write XML file
        xml_path = storage_path.parent / f"{sha256_hash}.xml"
        xml_path.write_bytes(xml_bytes)
        
        # Write metadata
        metadata = {
            "source_url": url,
            "cik": cik,
            "accession": accession,
            "as_of": as_of_date,
            "sha256": sha256_hash,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "size_bytes": len(xml_bytes),
        }
        
        metadata_path = storage_path.parent / "metadata.json"
        with metadata_path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        
        print(f"Saved to {xml_path}")
        print(f"SHA256: {sha256_hash}")
        
        return xml_path
    
    def _download_with_retry(self, url: str) -> Optional[bytes]:
        """Download with exponential backoff retry.
        
        Args:
            url: URL to download
            
        Returns:
            Downloaded bytes or None on failure
        """
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/xml,text/xml,*/*",
        }
        
        for attempt in range(self.MAX_RETRIES):
            self._throttle()
            
            try:
                response = requests.get(url, headers=headers, timeout=60)
                response.raise_for_status()
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
        cik: str,
        accession: str,
        as_of_date: str,
        sha256_hash: str,
    ) -> Path:
        """Build the storage path for a filing.
        
        Args:
            cik: CIK
            accession: Accession number
            as_of_date: Report date
            sha256_hash: File hash
            
        Returns:
            Path to metadata file location
        """
        # Structure: raw/sec/cik=<CIK>/accession=<ACCESSION>/as_of=<DATE>/
        path = (
            self.raw_data_dir
            / "sec"
            / f"cik={cik}"
            / f"accession={accession}"
            / f"as_of={as_of_date}"
        )
        return path / "metadata.json"
    
    def _throttle(self):
        """Ensure polite rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

