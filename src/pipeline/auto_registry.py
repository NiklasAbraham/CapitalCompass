"""Automatic fund registry population from ISINs.

Automatically discovers and populates fund_registry.yaml entries
for both US (N-PORT) and European (OAM) funds.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional
import yaml

try:
    import yfinance as yf
except ImportError:
    yf = None

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.ingest_nport import NPORTIngestionPipeline
from pipeline.ingest_oam import OAMIngestionPipeline
from pipeline.ingest_bdif import BDIFIngestionPipeline


class AutoRegistry:
    """Automatically populate fund registry from ISINs."""
    
    def __init__(
        self,
        registry_path: Optional[Path] = None,
        base_path: Optional[Path] = None,
    ):
        """Initialize auto-registry.
        
        Args:
            registry_path: Path to fund_registry.yaml
            base_path: Base data directory
        """
        if base_path:
            self.base_path = Path(base_path)
        else:
            project_root = Path(__file__).resolve().parent.parent.parent
            self.base_path = project_root / "data" / "pipeline"
        
        self.registry_path = (
            Path(registry_path) if registry_path
            else self.base_path / "fund_registry.yaml"
        )
        
        # Ensure registry file exists
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self._create_empty_registry()
    
    def _create_empty_registry(self):
        """Create an empty registry file."""
        with self.registry_path.open('w', encoding='utf-8') as f:
            yaml.dump({'funds': {}}, f, default_flow_style=False)
    
    def ensure_fund_registered(
        self,
        isin: Optional[str] = None,
        ticker: Optional[str] = None,
        asset_type: Optional[str] = None,
    ) -> Optional[str]:
        """Ensure a fund is registered, auto-populating if needed.
        
        Args:
            isin: ISIN identifier
            ticker: Ticker symbol
            asset_type: Asset type (stock or etf)
            
        Returns:
            Fund ID (ticker or ISIN) if registered, None otherwise
        """
        registry = self._load_registry()
        
        # Try to find existing entry
        fund_id = self._find_existing_entry(registry, isin, ticker)
        
        # Auto-detect asset type if not provided
        if not asset_type:
            asset_type = self._detect_asset_type(isin, ticker)
        
        # Only auto-register ETFs
        if asset_type != 'etf':
            return ticker or isin
        
        # If entry exists, check if it needs updates (e.g., missing auto_source)
        if fund_id:
            existing_entry = registry.get('funds', {}).get(fund_id)
            if isinstance(existing_entry, dict):
                # Check if we need to add missing fields
                needs_update = False
                if existing_entry.get('domicile') in ('LU', 'DE') and not existing_entry.get('auto_source'):
                    needs_update = True
                if not existing_entry.get('tickers') and ticker:
                    needs_update = True
                
                if needs_update:
                    # Discover updated entry
                    updated_entry = self._discover_fund_entry(isin, ticker)
                    if updated_entry:
                        self._add_registry_entry(registry, fund_id, updated_entry)
                return fund_id
        
        # Auto-populate new registry entry
        entry = self._discover_fund_entry(isin, ticker)
        if entry:
            fund_id = entry.get('fund_id') or ticker or isin
            self._add_registry_entry(registry, fund_id, entry)
            return fund_id
        
        return ticker or isin
    
    def _load_registry(self) -> Dict:
        """Load registry from YAML.
        
        Returns:
            Registry dictionary
        """
        if not self.registry_path.exists():
            return {'funds': {}}
        
        with self.registry_path.open('r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        return data
    
    def _find_existing_entry(
        self,
        registry: Dict,
        isin: Optional[str],
        ticker: Optional[str],
    ) -> Optional[str]:
        """Find existing registry entry.
        
        Args:
            registry: Registry dictionary
            isin: ISIN identifier
            ticker: Ticker symbol
            
        Returns:
            Fund ID if found, None otherwise
        """
        funds = registry.get('funds', {})
        
        # Check by ticker
        if ticker and ticker in funds:
            return ticker
        
        # Check by ISIN
        if isin:
            for fund_id, entry in funds.items():
                if isinstance(entry, dict):
                    if entry.get('share_class_isin') == isin or entry.get('isin') == isin:
                        return fund_id
                    # Also check if fund_id is the ISIN
                    if fund_id == isin:
                        return fund_id
        
        return None
    
    def _detect_asset_type(
        self,
        isin: Optional[str],
        ticker: Optional[str],
    ) -> str:
        """Detect if asset is stock or ETF.
        
        Args:
            isin: ISIN identifier
            ticker: Ticker symbol
            
        Returns:
            'stock' or 'etf'
        """
        # Try yfinance to detect
        if yf and ticker:
            try:
                ticker_obj = yf.Ticker(ticker)
                info = ticker_obj.info
                quote_type = info.get('quoteType', '').upper()
                if quote_type in ('ETF', 'MUTUALFUND'):
                    return 'etf'
                elif quote_type == 'EQUITY':
                    return 'stock'
            except Exception:
                pass
        
        # Default: assume ETF if we have ISIN but no clear indicator
        # Most ISIN-only entries in configs are ETFs
        if isin and not ticker:
            return 'etf'
        
        return 'etf'  # Conservative default
    
    def _discover_fund_entry(
        self,
        isin: Optional[str],
        ticker: Optional[str],
    ) -> Optional[Dict]:
        """Discover fund entry from ISIN or ticker.
        
        Args:
            isin: ISIN identifier
            ticker: Ticker symbol
            
        Returns:
            Fund entry dictionary or None
        """
        if not isin and not ticker:
            return None
        
        # Determine domicile from ISIN
        domicile = None
        if isin and len(isin) >= 2:
            domicile = isin[:2]
        
        entry = {
            'fund_id': ticker or isin,
            'share_class_isin': isin,
            'domicile': domicile,
        }
        
        # Try to find ticker from ISIN using PrimaryHoldingsClient
        if isin and not ticker:
            try:
                from pipeline.primary_holdings import PrimaryHoldingsClient
                client = PrimaryHoldingsClient(registry_path=self.registry_path)
                # Try to resolve by ISIN
                registry = self._load_registry()
                funds = registry.get('funds', {})
                for fund_id, fund_entry in funds.items():
                    if isinstance(fund_entry, dict):
                        if fund_entry.get('share_class_isin') == isin or fund_entry.get('isin') == isin:
                            tickers = fund_entry.get('tickers', [])
                            if tickers:
                                ticker = tickers[0] if isinstance(tickers, list) else tickers
                                entry['fund_id'] = ticker
                                break
            except Exception:
                pass
        
        # Try to get metadata from yfinance
        test_ticker = ticker or isin
        if yf and test_ticker:
            try:
                ticker_obj = yf.Ticker(test_ticker)
                info = ticker_obj.info
                
                entry['name'] = info.get('longName') or info.get('shortName', test_ticker)
                entry['issuer'] = info.get('fundFamily') or info.get('companyName', 'Unknown')
                
                # Update ticker if we found one
                if not ticker and 'symbol' in info:
                    ticker = info.get('symbol')
                    entry['fund_id'] = ticker
                    entry['tickers'] = [ticker]
                
                # Also try searching by ISIN if direct lookup failed
                if not ticker and isin:
                    # Try common ISIN-to-ticker patterns
                    # Some exchanges use ISIN as ticker with suffix
                    for suffix in ['.PA', '.AS', '.DE', '.L', '.SW']:
                        test_ticker_with_suffix = isin + suffix
                        try:
                            test_obj = yf.Ticker(test_ticker_with_suffix)
                            test_info = test_obj.info
                            if test_info and test_info.get('isin') == isin:
                                ticker = test_ticker_with_suffix
                                entry['fund_id'] = ticker
                                entry['tickers'] = [ticker]
                                break
                        except:
                            continue
                
                # Try to get CIK for US funds
                if domicile == 'US':
                    cik = info.get('cik')
                    if cik:
                        entry['cik'] = str(cik).zfill(10)
                        entry['freshness_days'] = 30
                        entry['gold_path'] = f"fund_id={ticker or isin}"
                        if ticker:
                            entry['tickers'] = [ticker]
                        return entry
            except Exception:
                pass
        
        # For European funds, set up OAM entry
        if domicile in ('LU', 'DE') and isin:
            entry['isin'] = isin  # Use isin as key for OAM
            entry['oam'] = 'LuxSE' if domicile == 'LU' else 'Bundesanzeiger'
            entry['freshness_days'] = 210
            entry['gold_path'] = f"isin={isin}"
            # Set auto_source as fallback if OAM fails - always set this
            entry['auto_source'] = 'yfinance'
            if ticker:
                entry['tickers'] = [ticker]
            elif test_ticker and test_ticker != isin:
                # Use the ticker we found from yfinance
                entry['tickers'] = [test_ticker]
            # Use ISIN as fund_id for OAM
            entry['fund_id'] = isin
            return entry
        
        # Fallback: use yfinance as auto_source
        if ticker or isin:
            entry['auto_source'] = 'yfinance'
            entry['freshness_days'] = 30
            entry['gold_path'] = f"fund_id={ticker or isin}"
            if ticker:
                entry['tickers'] = [ticker]
            return entry
        
        return None
    
    def _add_registry_entry(self, registry: Dict, fund_id: str, entry: Dict):
        """Add entry to registry and save.
        
        Args:
            registry: Registry dictionary
            fund_id: Fund identifier
            entry: Fund entry dictionary
        """
        if 'funds' not in registry:
            registry['funds'] = {}
        
        # Merge with existing entry if present
        if fund_id in registry['funds']:
            existing = registry['funds'][fund_id]
            if isinstance(existing, dict):
                # Update existing entry with new fields, but preserve important existing ones
                for key, value in entry.items():
                    if value is not None:  # Only update non-None values
                        existing[key] = value
                # Ensure auto_source is set for European funds if missing
                if existing.get('domicile') in ('LU', 'DE') and not existing.get('auto_source'):
                    existing['auto_source'] = 'yfinance'
                entry = existing
            else:
                # Replace non-dict entry
                registry['funds'][fund_id] = entry
        else:
            registry['funds'][fund_id] = entry
        
        # Ensure auto_source is set for European funds
        final_entry = registry['funds'][fund_id]
        if isinstance(final_entry, dict):
            if final_entry.get('domicile') in ('LU', 'DE') and not final_entry.get('auto_source'):
                final_entry['auto_source'] = 'yfinance'
        
        # Save registry
        with self.registry_path.open('w', encoding='utf-8') as f:
            yaml.dump(registry, f, default_flow_style=False, sort_keys=False)
        
        print(f"Auto-registered fund: {fund_id}")
    
    def ensure_holdings_available(
        self,
        fund_id: str,
        isin: Optional[str] = None,
        ticker: Optional[str] = None,
    ) -> bool:
        """Ensure holdings are available, pulling if needed.
        
        Args:
            fund_id: Fund identifier
            isin: ISIN identifier
            ticker: Ticker symbol
            
        Returns:
            True if holdings are available or can be fetched
        """
        registry = self._load_registry()
        funds = registry.get('funds', {})
        entry = funds.get(fund_id)
        
        # If entry not found, try to find by ISIN
        if not entry and isin:
            for fid, e in funds.items():
                if isinstance(e, dict):
                    if e.get('share_class_isin') == isin or e.get('isin') == isin:
                        entry = e
                        fund_id = fid
                        break
        
        if not entry:
            # Try auto_snapshot for unknown funds
            try:
                from pipeline.auto_snapshot import AutoSnapshotManager
                snapshot_mgr = AutoSnapshotManager(self.base_path, {'funds': {}})
                temp_entry = {'fund_id': fund_id, 'isin': isin}
                if ticker:
                    temp_entry['tickers'] = [ticker]
                result = snapshot_mgr.ensure_snapshot(temp_entry, None)
                return result.success
            except Exception:
                return False
        
        # Check if holdings exist
        domicile = entry.get('domicile', '')
        isin_identifier = entry.get('share_class_isin') or entry.get('isin') or isin
        
        if domicile == 'US' and entry.get('cik'):
            # Use N-PORT pipeline
            try:
                pipeline = NPORTIngestionPipeline(
                    base_path=self.base_path,
                    registry_path=self.registry_path,
                )
                return pipeline.ingest_fund(fund_id, force=False)
            except Exception as e:
                print(f"Failed to ingest N-PORT for {fund_id}: {e}")
                return False
        
        elif domicile in ('LU', 'DE') and isin_identifier:
            # Use OAM pipeline
            try:
                pipeline = OAMIngestionPipeline(
                    base_path=self.base_path,
                    registry_path=self.registry_path,
                )
                return pipeline.ingest_fund(isin_identifier, force=False)
            except Exception as e:
                print(f"Failed to ingest OAM for {isin_identifier}: {e}")
                return False

        elif domicile == 'FR' and isin_identifier:
            # Use BDIF pipeline
            try:
                pipeline = BDIFIngestionPipeline(
                    base_path=self.base_path,
                    registry_path=self.registry_path,
                )
                return pipeline.ingest_fund(fund_id, force=False)
            except Exception as e:
                print(f"Failed to ingest BDIF for {fund_id}: {e}")
                return False
        
        # For other cases, auto_snapshot will handle it via PrimaryHoldingsClient
        return True
