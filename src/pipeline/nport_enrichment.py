"""N-PORT holdings enrichment module.

Enriches silver holdings data with computed weights, normalized identifiers,
and standardized classifications to produce gold-layer data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import pandas as pd


class NPORTEnrichment:
    """Enrich holdings data from silver to gold layer."""
    
    def __init__(self, reference_dir: Optional[Path] = None):
        """Initialize enrichment module.
        
        Args:
            reference_dir: Directory containing reference data (e.g., CUSIP-to-ISIN mapping)
        """
        self.reference_dir = reference_dir
        self._cusip_to_isin = None
    
    def enrich_holdings(self, silver_df: pd.DataFrame) -> pd.DataFrame:
        """Enrich silver holdings to gold quality.
        
        Args:
            silver_df: Silver layer holdings DataFrame
            
        Returns:
            Gold layer holdings DataFrame with computed weights and enriched data
        """
        if silver_df.empty:
            return silver_df.copy()
        
        gold_df = silver_df.copy()
        
        # Step 1: Resolve ISIN identifiers
        gold_df = self._resolve_isin(gold_df)
        
        # Step 2: Compute weights
        gold_df = self._compute_weights(gold_df)
        
        # Step 3: Normalize classifications
        gold_df = self._normalize_classifications(gold_df)
        
        # Step 4: Add enrichment metadata
        gold_df['enrichment_version'] = 1
        
        return gold_df
    
    def _resolve_isin(self, df: pd.DataFrame) -> pd.DataFrame:
        """Resolve ISIN identifiers from CUSIP when missing.
        
        Args:
            df: DataFrame with holdings
            
        Returns:
            DataFrame with resolved ISINs
        """
        # If ISIN is missing but CUSIP is present, try to resolve
        if 'isin' in df.columns and 'cusip' in df.columns:
            missing_isin = df['isin'].isna() & df['cusip'].notna()
            
            if missing_isin.any():
                # Load CUSIP-to-ISIN mapping if available
                if self.reference_dir and self._cusip_to_isin is None:
                    mapping_path = self.reference_dir / "cusip_to_isin.csv"
                    if mapping_path.exists():
                        self._cusip_to_isin = pd.read_csv(mapping_path)
                
                # Apply mapping
                if self._cusip_to_isin is not None:
                    cusip_map = dict(
                        zip(
                            self._cusip_to_isin['cusip'],
                            self._cusip_to_isin['isin']
                        )
                    )
                    df.loc[missing_isin, 'isin'] = (
                        df.loc[missing_isin, 'cusip'].map(cusip_map)
                    )
        
        # Create a unified identifier column
        if 'isin' in df.columns:
            df['instrument_isin'] = df['isin']
        if 'instrument_isin' not in df.columns and 'cusip' in df.columns:
            df['instrument_isin'] = df['cusip']
        
        return df
    
    def _compute_weights(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute position weights as percentage of total.
        
        Args:
            df: DataFrame with holdings
            
        Returns:
            DataFrame with weight_pct column
        """
        if 'market_value_local' not in df.columns:
            print("Warning: market_value_local not found, cannot compute weights")
            return df
        
        # Convert to numeric, handling any errors
        market_values = pd.to_numeric(df['market_value_local'], errors='coerce')
        
        # Remove negative values (shorts) for weight calculation
        positive_values = market_values.copy()
        positive_values[positive_values < 0] = 0
        
        total_value = positive_values.sum()
        
        if total_value > 0:
            df['weight_pct'] = (positive_values / total_value) * 100.0
        else:
            print("Warning: Total market value is zero or negative")
            df['weight_pct'] = 0.0
        
        # Also store absolute market value in EUR/USD for consistency
        df['market_value_eur'] = market_values  # Assume USD ~= EUR or convert if needed
        
        return df
    
    def _normalize_classifications(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize country, sector, and asset class fields.
        
        Args:
            df: DataFrame with holdings
            
        Returns:
            DataFrame with normalized classification columns
        """
        # Normalize country codes to ISO 3166-1 alpha-2
        if 'country_raw' in df.columns:
            df['country'] = df['country_raw'].fillna('UNKNOWN').str.upper()
            # Map common variations
            country_map = {
                'US': 'US',
                'USA': 'US',
                'UNITED STATES': 'US',
                'GB': 'GB',
                'UK': 'GB',
                'UNITED KINGDOM': 'GB',
                'UNKNOWN': 'Unknown',
                '': 'Unknown',
            }
            df['country'] = df['country'].replace(country_map)
        
        # Normalize asset categories
        if 'category_raw' in df.columns:
            df['asset_class'] = df['category_raw'].fillna('Unknown').str.title()
            
            # Map N-PORT categories to standard asset classes
            asset_class_map = {
                'Equity': 'Equity',
                'Equity-common': 'Equity',
                'Equity-preferred': 'Equity',
                'Debt': 'Fixed Income',
                'Debt-corporate': 'Fixed Income',
                'Debt-government': 'Fixed Income',
                'Debt-sovereign': 'Fixed Income',
                'Convertible': 'Fixed Income',
                'Derivative-equity': 'Derivatives',
                'Derivative-commodity': 'Derivatives',
                'Derivative-credit': 'Derivatives',
                'Derivative-foreign Exchange': 'Derivatives',
                'Derivative-interest Rate': 'Derivatives',
                'Repurchase Agreement': 'Cash',
                'Cash': 'Cash',
                'Unknown': 'Other',
                '': 'Other',
            }
            df['asset_class'] = df['asset_class'].replace(asset_class_map)
        
        # Add sector classification (would need external enrichment for real data)
        if 'sector' not in df.columns:
            df['sector'] = 'Unknown'
        
        # Normalize instrument names
        if 'instrument_name_raw' in df.columns:
            df['instrument_name'] = df['instrument_name_raw'].str.strip()
        
        return df

