"""BDIF holdings enrichment module."""

from __future__ import annotations

import pandas as pd


class BDIFEnrichment:
    """Enrich BDIF silver holdings to gold quality."""

    def enrich_holdings(self, silver_df: pd.DataFrame) -> pd.DataFrame:
        if silver_df.empty:
            return silver_df.copy()

        gold_df = silver_df.copy()

        gold_df["isin"] = gold_df.get("isin").astype(str).str.upper()
        gold_df.loc[gold_df["isin"].isin(["nan", "None"]), "isin"] = None

        if "weight_pct" not in gold_df.columns or gold_df["weight_pct"].isna().all():
            gold_df = self._compute_weights(gold_df)

        gold_df["country"] = gold_df.get("country_raw")
        missing_country = gold_df["country"].isna() | (gold_df["country"] == "")
        gold_df.loc[missing_country, "country"] = gold_df["isin"].str[:2]
        gold_df["country"] = gold_df["country"].fillna("Unknown").str.upper()

        gold_df["enrichment_version"] = 1

        return gold_df

    def _compute_weights(self, df: pd.DataFrame) -> pd.DataFrame:
        if "market_value_eur" not in df.columns:
            df["weight_pct"] = 0.0
            return df

        values = pd.to_numeric(df["market_value_eur"], errors="coerce")
        values = values.fillna(0.0)
        total = values.sum()
        if total > 0:
            df["weight_pct"] = (values / total) * 100.0
        else:
            df["weight_pct"] = 0.0
        return df
