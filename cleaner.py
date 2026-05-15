"""
cleaner.py
----------
Core cleaning transformations for CHW reporting data.

Key principle: document everything. In health systems,
data lineage is not optional. Every transformation is
logged with a reason code so it can be reviewed or reversed.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class AuditLog:
    """Tracks every transformation applied to the dataset."""

    def __init__(self):
        self.entries = []

    def log(self, field: str, action: str, reason: str, rows_affected: int, old_value=None, new_value=None):
        self.entries.append({
            "timestamp": datetime.utcnow().isoformat(),
            "field": field,
            "action": action,
            "reason": reason,
            "rows_affected": rows_affected,
            "old_value_sample": str(old_value)[:100] if old_value is not None else None,
            "new_value_sample": str(new_value)[:100] if new_value is not None else None,
        })

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.entries)

    def summary(self) -> Dict:
        return {
            "total_transformations": len(self.entries),
            "fields_touched": list(set(e["field"] for e in self.entries)),
            "total_rows_affected": sum(e["rows_affected"] for e in self.entries),
        }


class CHWDataCleaner:
    """
    Cleans raw CHW data for AI-ready analytics.

    Handles:
    - Date format standardisation (multi-format, multi-country)
    - Missing value flagging (not imputation)
    - Field name normalisation
    - Data type coercion
    - Value range validation

    Does NOT handle:
    - Deduplication (see deduplicator.py)
    - Country-specific schema mapping (see country_mapper.py)
    """

    # Supported date formats — ordered most to least specific
    DATE_FORMATS = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%Y%m%d",
        "%d.%m.%Y",
    ]

    def __init__(self, df: pd.DataFrame, country_code: str = "UNKNOWN"):
        self.df = df.copy()
        self.country_code = country_code
        self.audit = AuditLog()
        self._flag_col = "__data_quality_flags__"
        self.df[self._flag_col] = ""

    def run(self) -> Tuple[pd.DataFrame, AuditLog]:
        """Run full cleaning pipeline."""
        logger.info(f"Starting cleaning pipeline | Country: {self.country_code} | Rows: {len(self.df)}")

        self._normalise_column_names()
        self._standardise_date_fields()
        self._flag_missing_values()
        self._coerce_numeric_fields()
        self._trim_whitespace()

        logger.info(f"Cleaning complete. Transformations: {len(self.audit.entries)}")
        return self.df, self.audit

    def _normalise_column_names(self):
        """Standardise column names to snake_case lowercase."""
        old_cols = list(self.df.columns)
        new_cols = [
            col.strip().lower().replace(" ", "_").replace("-", "_")
            for col in old_cols
        ]
        rename_map = {o: n for o, n in zip(old_cols, new_cols) if o != n}
        if rename_map:
            self.df.rename(columns=rename_map, inplace=True)
            self.audit.log(
                field="ALL_COLUMNS",
                action="NORMALISE_COLUMN_NAMES",
                reason="Standardise to snake_case for consistent downstream processing",
                rows_affected=0,
                old_value=list(rename_map.keys()),
                new_value=list(rename_map.values())
            )

    def _standardise_date_fields(self):
        """
        Detect and standardise date fields to ISO 8601 (YYYY-MM-DD).

        We detect format per-value rather than assuming a single format
        because multi-country deployments often have mixed formats
        in the same column — especially when data was migrated or
        collected by different tools at different times.
        """
        date_keywords = ["date", "time", "visit", "created", "updated", "dob", "birth"]
        date_cols = [c for c in self.df.columns if any(kw in c for kw in date_keywords)]

        for col in date_cols:
            converted = 0
            failed = 0
            original_values = self.df[col].copy()

            def parse_date(val):
                nonlocal converted, failed
                if pd.isna(val):
                    return val
                val_str = str(val).strip()
                for fmt in self.DATE_FORMATS:
                    try:
                        parsed = datetime.strptime(val_str, fmt)
                        converted += 1
                        return parsed.strftime("%Y-%m-%d")
                    except ValueError:
                        continue
                # If all formats fail, flag and preserve original
                failed += 1
                return val_str

            self.df[col] = self.df[col].apply(parse_date)

            if converted > 0 or failed > 0:
                self.audit.log(
                    field=col,
                    action="STANDARDISE_DATE_FORMAT",
                    reason=f"Normalise to ISO 8601 (YYYY-MM-DD). Multi-format detection used.",
                    rows_affected=converted,
                    old_value=f"Mixed formats",
                    new_value=f"YYYY-MM-DD | {failed} values could not be parsed (preserved as-is)"
                )

            if failed > 0:
                self._add_flag(
                    col,
                    f"DATE_PARSE_FAILED:{failed}_values",
                    rows_where=self.df[col].apply(
                        lambda x: not self._is_iso_date(str(x)) and pd.notna(x)
                    )
                )

    def _flag_missing_values(self):
        """
        Flag missing values rather than imputing them.

        Rationale: In AI-driven health analytics, imputed values
        can introduce systematic bias — especially if missingness
        is not random (e.g. certain communities consistently have
        missing fields due to connectivity issues). We preserve
        the missingness signal and flag it for downstream handling.
        """
        for col in self.df.columns:
            if col == self._flag_col:
                continue
            null_mask = self.df[col].isnull()
            null_count = null_mask.sum()
            if null_count > 0:
                self._add_flag(f"MISSING_{col.upper()}", "NULL_VALUE", rows_where=null_mask)
                self.audit.log(
                    field=col,
                    action="FLAG_MISSING",
                    reason="Preserve missingness signal. Imputation not applied — bias risk in health analytics.",
                    rows_affected=int(null_count)
                )

    def _coerce_numeric_fields(self):
        """Attempt numeric coercion on fields that should be numeric."""
        numeric_keywords = ["age", "count", "number", "num", "total", "amount", "score", "weight", "height"]
        numeric_cols = [c for c in self.df.columns if any(kw in c for kw in numeric_keywords)]

        for col in numeric_cols:
            original = self.df[col].copy()
            coerced = pd.to_numeric(self.df[col], errors="coerce")
            new_nulls = coerced.isnull().sum() - original.isnull().sum()

            if new_nulls > 0:
                self.df[col] = coerced
                self._add_flag(col, f"NON_NUMERIC_COERCED_TO_NULL:{new_nulls}", rows_where=coerced.isnull() & original.notna())
                self.audit.log(
                    field=col,
                    action="COERCE_NUMERIC",
                    reason="Expected numeric field — non-numeric values set to null and flagged.",
                    rows_affected=int(new_nulls)
                )

    def _trim_whitespace(self):
        """Strip leading/trailing whitespace from string fields."""
        str_cols = self.df.select_dtypes(include="object").columns
        for col in str_cols:
            if col == self._flag_col:
                continue
            trimmed = self.df[col].str.strip() if self.df[col].dtype == object else self.df[col]
            changed = (trimmed != self.df[col]).sum()
            if changed > 0:
                self.df[col] = trimmed
                self.audit.log(
                    field=col,
                    action="TRIM_WHITESPACE",
                    reason="Remove leading/trailing whitespace",
                    rows_affected=int(changed)
                )

    def _add_flag(self, field_or_label: str, flag_type: str, rows_where=None):
        """Add a data quality flag to the flag column."""
        flag_str = f"{field_or_label}:{flag_type}"
        if rows_where is not None:
            self.df.loc[rows_where, self._flag_col] = (
                self.df.loc[rows_where, self._flag_col]
                .apply(lambda x: f"{x}|{flag_str}" if x else flag_str)
            )
        else:
            self.df[self._flag_col] = self.df[self._flag_col].apply(
                lambda x: f"{x}|{flag_str}" if x else flag_str
            )

    def _is_iso_date(self, val: str) -> bool:
        try:
            datetime.strptime(val, "%Y-%m-%d")
            return True
        except ValueError:
            return False
