"""Date normalization helpers for factor rotation data."""

from __future__ import annotations

import pandas as pd


def normalize_date_series(values: pd.Series) -> pd.Series:
    """Normalize common date representations to YYYY-MM-DD strings."""
    if values.empty:
        return values.astype(str)
    if pd.api.types.is_datetime64_any_dtype(values):
        return values.dt.strftime("%Y-%m-%d")
    raw_text = values.astype(str)
    sample = raw_text.dropna().head(2048)
    if (
        not sample.empty
        and bool(sample.str.len().eq(10).all())
        and bool(sample.str.slice(4, 5).eq("-").all())
        and bool(sample.str.slice(7, 8).eq("-").all())
    ):
        return raw_text
    return pd.to_datetime(values).dt.strftime("%Y-%m-%d")
