"""
profiler.py
-----------
Dataset auditing and profiling for CHW reporting data.

Before cleaning anything, we understand what we have.
Rushing to clean messy health data without profiling first
leads to assumptions that corrupt downstream AI analytics.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataProfiler:
    """
    Profiles a raw CHW dataset to understand its quality
    before any transformations are applied.

    Design principle: audit first, clean second.
    """

    def __init__(self, df: pd.DataFrame, country_code: str = "UNKNOWN"):
        self.df = df.copy()
        self.country_code = country_code
        self.profile = {}
        self.profiled_at = datetime.utcnow().isoformat()

    def run(self) -> Dict[str, Any]:
        """Run full profiling suite and return profile report."""
        logger.info(f"Profiling dataset: {len(self.df)} rows, {len(self.df.columns)} columns | Country: {self.country_code}")

        self.profile = {
            "country_code": self.country_code,
            "profiled_at": self.profiled_at,
            "row_count": len(self.df),
            "column_count": len(self.df.columns),
            "columns": self._profile_columns(),
            "duplicates": self._profile_duplicates(),
            "date_fields": self._detect_date_fields(),
            "completeness_score": self._completeness_score(),
            "flags": self._generate_flags(),
        }

        self._log_summary()
        return self.profile

    def _profile_columns(self) -> Dict[str, Any]:
        """Profile each column: null rate, unique values, data type."""
        col_profiles = {}
        for col in self.df.columns:
            null_count = self.df[col].isnull().sum()
            null_rate = round(null_count / len(self.df), 4)
            unique_count = self.df[col].nunique()

            col_profiles[col] = {
                "dtype": str(self.df[col].dtype),
                "null_count": int(null_count),
                "null_rate": null_rate,
                "unique_values": int(unique_count),
                "sample_values": self.df[col].dropna().head(3).tolist(),
            }

            # Flag high null rates
            if null_rate > 0.2:
                col_profiles[col]["warning"] = f"High null rate: {null_rate:.1%}"

        return col_profiles

    def _profile_duplicates(self) -> Dict[str, Any]:
        """
        Detect duplicates — but don't drop them yet.
        In CHW systems, duplicates often have legitimate causes
        (two workers visiting same household, sync conflicts).
        We document, not destroy.
        """
        total_dupes = self.df.duplicated().sum()

        # Check for soft duplicates (same record ID, different timestamps)
        id_cols = [c for c in self.df.columns if any(
            keyword in c.lower() for keyword in ["id", "record", "uuid", "household"]
        )]

        soft_dupes = 0
        if id_cols:
            soft_dupes = self.df.duplicated(subset=id_cols, keep=False).sum()

        return {
            "exact_duplicates": int(total_dupes),
            "soft_duplicates_by_id": int(soft_dupes),
            "id_columns_used": id_cols,
            "note": "Duplicates flagged for review, not auto-dropped. CHW duplicates often reflect legitimate multi-visit scenarios."
        }

    def _detect_date_fields(self) -> Dict[str, Any]:
        """
        Detect fields that look like dates and identify format inconsistencies.
        Multi-country deployments often have mixed date formats in the same field.
        """
        date_fields = {}
        date_keywords = ["date", "time", "visit", "created", "updated", "dob", "birth"]

        for col in self.df.columns:
            if any(kw in col.lower() for kw in date_keywords):
                sample = self.df[col].dropna().head(20).astype(str).tolist()
                formats_detected = self._detect_formats(sample)
                date_fields[col] = {
                    "sample_values": sample[:5],
                    "formats_detected": formats_detected,
                    "needs_standardisation": len(formats_detected) > 1
                }

        return date_fields

    def _detect_formats(self, samples: list) -> list:
        """Detect date formats present in a sample of values."""
        format_patterns = [
            "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
            "%d-%m-%Y", "%Y%m%d", "%d.%m.%Y",
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"
        ]
        detected = set()
        for val in samples:
            for fmt in format_patterns:
                try:
                    datetime.strptime(str(val).strip(), fmt)
                    detected.add(fmt)
                    break
                except (ValueError, TypeError):
                    continue
        return list(detected)

    def _completeness_score(self) -> float:
        """
        Overall completeness score (0-1).
        Simple metric: proportion of non-null values across all cells.
        """
        total_cells = self.df.size
        null_cells = self.df.isnull().sum().sum()
        return round(1 - (null_cells / total_cells), 4) if total_cells > 0 else 0.0

    def _generate_flags(self) -> list:
        """Generate human-readable flags for issues requiring attention."""
        flags = []

        # Completeness flag
        score = self._completeness_score()
        if score < 0.8:
            flags.append({
                "level": "WARNING",
                "message": f"Dataset completeness is {score:.1%}. Consider reviewing data collection protocols."
            })

        # Duplicate flag
        dupe_info = self._profile_duplicates()
        if dupe_info["exact_duplicates"] > 0:
            flags.append({
                "level": "INFO",
                "message": f"{dupe_info['exact_duplicates']} exact duplicates detected. Human review recommended before resolution."
            })

        # Date format inconsistency flag
        date_fields = self._detect_date_fields()
        for field, info in date_fields.items():
            if info.get("needs_standardisation"):
                flags.append({
                    "level": "WARNING",
                    "message": f"Field '{field}' contains mixed date formats: {info['formats_detected']}. Standardisation required."
                })

        return flags

    def _log_summary(self):
        """Log a human-readable summary to console."""
        logger.info("=" * 60)
        logger.info(f"PROFILE SUMMARY | Country: {self.country_code}")
        logger.info(f"Rows: {self.profile['row_count']} | Columns: {self.profile['column_count']}")
        logger.info(f"Completeness Score: {self.profile['completeness_score']:.1%}")
        logger.info(f"Exact Duplicates: {self.profile['duplicates']['exact_duplicates']}")
        logger.info(f"Flags: {len(self.profile['flags'])}")
        for flag in self.profile["flags"]:
            logger.info(f"  [{flag['level']}] {flag['message']}")
        logger.info("=" * 60)

    def to_dict(self) -> Dict[str, Any]:
        return self.profile
