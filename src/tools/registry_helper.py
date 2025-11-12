#!/usr/bin/env python
"""
registry_helper.py

Utility script to draft `fund_registry.yaml` entries by combining yfinance
metadata with SEC Form N-PORT discovery.

Usage (example):
    conda activate capital
    python src/tools/registry_helper.py --isin LU2581375156 --guess-ticker IWLD.AS

If the fund files N-PORT with the SEC, the script returns the CIK / series /
class identifiers. Otherwise it produces a yfinance-based suggestion that you
can augment with fallback holdings.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Optional

import requests

try:
    import yfinance as yf  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "yfinance is required: pip install yfinance (within the capital environment)"
    ) from exc


USER_AGENT = "CapitalCompassBot/1.0 (registry helper; support@capitalcompass.ai)"
SEC_SEARCH_ENDPOINT = "https://efts.sec.gov/LATEST/search-index"

# Edit this list to evaluate additional ISIN / ticker pairs.
# Each tuple is (ISIN, yahoo_ticker_or_None)
REQUESTS: list[tuple[str, Optional[str]]] = [
    ("LU2581375156", "XSX7.DE"),
    ("US78462F1030", "SPY"),
]


@dataclass
class RegistrySuggestion:
    fund_id: str
    cik: Optional[str]
    series_id: Optional[str]
    class_id: Optional[str]
    issuer: Optional[str]
    name: Optional[str]
    domicile: Optional[str]
    share_class_isin: str
    gold_path: str
    freshness_days: int = 30
    tickers: Optional[list[str]] = None
    auto_source: Optional[str] = None
    fallback_holdings: Optional[list[dict]] = None


def _search_sec(term: str) -> list[dict]:
    params = {
        "q": term,
        "from": "0",
        "size": "20",
    }
    resp = requests.get(
        SEC_SEARCH_ENDPOINT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("hits", {}).get("hits", [])


def _fetch_series_and_class(
    cik: str, accession: str
) -> tuple[Optional[str], Optional[str]]:
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession.replace('-', '')}/primary_doc.xml"
    )
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()

    from lxml import etree  # type: ignore

    root = etree.fromstring(resp.content)
    ns = {"n": "http://www.sec.gov/edgar/nport"}
    series = root.xpath("string(.//n:seriesId)", namespaces=ns) or None
    class_ids = root.xpath(".//n:seriesClassInfo/n:classId/text()", namespaces=ns)
    class_id = class_ids[0] if class_ids else None
    return series, class_id


def build_registry_suggestion(
    isin: str, ticker_hint: Optional[str]
) -> RegistrySuggestion:
    ticker = ticker_hint or isin
    yf_ticker = yf.Ticker(ticker)
    info = yf_ticker.info

    issuer = info.get("fundFamily") or info.get("issuer")
    name = info.get("longName") or info.get("shortName") or ticker
    domicile = info.get("country") or info.get("countryOfOrigin")

    suggestion = RegistrySuggestion(
        fund_id=isin,
        cik=None,
        series_id=None,
        class_id=None,
        issuer=issuer,
        name=name,
        domicile=domicile,
        share_class_isin=isin,
        gold_path=f"fund_id={isin}",
        tickers=[ticker],
        auto_source="yfinance",
    )

    # Check if this is a European UCITS fund (ISIN starts with country code)
    is_european_ucits = isin.startswith(("LU", "IE", "FR", "DE", "NL", "CH"))

    if is_european_ucits:
        # European UCITS funds don't file N-PORT with SEC
        # They report to national regulators (CSSF for Luxembourg, Central Bank of Ireland, etc.)
        # Holdings data is typically available from:
        # 1. Fund manager websites (CSV/PDF downloads)
        # 2. e-file.lu (Luxembourg) - but not publicly accessible via API
        # 3. ESMA databases - but holdings not directly available
        # Note: yfinance will only provide top holdings (limited)
        # For full holdings, check the fund manager's website or use fallback_holdings
        return suggestion

    # Search SEC filings for US-domiciled funds
    hits = _search_sec(f'"{name}" "NPORT"')
    for hit in hits:
        accession = hit["_source"].get("adsh")
        ciks = hit["_source"].get("ciks", [])
        if not accession or not ciks:
            continue

        for cik in ciks:
            try:
                series_id, class_id = _fetch_series_and_class(cik, accession)
            except Exception:
                continue

            if series_id and class_id:
                suggestion.cik = cik.zfill(10)
                suggestion.series_id = series_id
                suggestion.class_id = class_id
                suggestion.auto_source = None  # prefer N-PORT ingestion
                return suggestion

            time.sleep(0.2)

    return suggestion


def main():
    for isin, ticker in REQUESTS:
        suggestion = build_registry_suggestion(isin, ticker)
        output = asdict(suggestion)

        # Add helpful note for European UCITS funds
        if isin.startswith(("LU", "IE", "FR", "DE", "NL", "CH")):
            output["_note"] = (
                "European UCITS fund: No SEC N-PORT filing available. "
                "For full holdings, check the fund manager's website for CSV/PDF downloads, "
                "or manually curate holdings and add to 'fallback_holdings' in fund_registry.yaml. "
                "yfinance will only provide limited top holdings."
            )

        print(json.dumps(output, indent=2))
        print()  # spacer between entries


if __name__ == "__main__":
    main()
