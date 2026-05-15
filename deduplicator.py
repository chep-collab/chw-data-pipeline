"""
deduplicator.py
---------------
Duplicate detection and resolution for CHW datasets.

Key principle: Never silently drop duplicates in health data.
Duplicates in CHW systems often have legitimate causes:
  - Two health workers visiting the same household
  - Sync conflicts from offline data collection
  - Data migration artefacts

We flag, classify, and document — not destroy.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Optional, Dict
import logging

logger = logging.getLogger(__name__)

# Resolution reason codes
REASON_EXACT_DUPLICATE = "EXACT_DUPLICATE"
REASON_SYNC_CONFLICT = "SYNC_CONFLICT"
REASON_MULTI_VISIT = "MULTI_VISIT"
REASON_UNKNOWN = "UNKNOWN_DUPLICATE"


class Deduplicator:
    """
    Detects and resolves duplicate records in CHW data.

    Strategy: timestamp + source_id based resolution.
    When duplicates are found, we keep the most recent record
    as primary and mark others as secondary with a reason code.
    This preserves all information while preventing double-counting
    in analytics.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        id_columns: List[str],
        timestamp_column: Optional[str] = None,
        source_column: Optional[str] = None,
    ):
        self.df = df.copy()
        self.id_columns = id_columns
        self.timestamp_column = timestamp_column
        self.source_column = source_column
        self.resolution_log = []

    def run(self) -> pd.DataFrame:
        """
        Run deduplication. Returns dataframe with duplicate flags added.
        Does NOT remove records — marks them for downstream handling.
        """
        logger.info(f"Starting deduplication | Rows: {len(self.df)}")

        self.df["__duplicate_status__"] = "PRIMARY"
        self.df["__duplicate_reason__"] = ""
        self.df["__duplicate_group_id__"] = ""

        exact_dupes = self._find_exact_duplicates()
        soft_dupes = self._find_soft_duplicates()

        logger.info(
            f"Deduplication complete | "
            f"Exact: {exact_dupes} | Soft: {soft_dupes} | "
            f"Total flagged: {(self.df['__duplicate_status__'] == 'SECONDARY').sum()}"
        )

        return self.df

    def _find_exact_duplicates(self) -> int:
        """Find and flag rows that are completely identical."""
        dupe_mask = self.df.duplicated(
            subset=[c for c in self.df.columns if not c.startswith("__")],
            keep="first"
        )
        count = dupe_mask.sum()
        if count > 0:
            self.df.loc[dupe_mask, "__duplicate_status__"] = "SECONDARY"
            self.df.loc[dupe_mask, "__duplicate_reason__"] = REASON_EXACT_DUPLICATE
            self._log_resolution(REASON_EXACT_DUPLICATE, int(count))
            logger.info(f"Exact duplicates flagged: {count}")
        return int(count)

    def _find_soft_duplicates(self) -> int:
        """
        Find records with matching IDs but different timestamps or sources.
        These are the most important to handle carefully in CHW data.
        """
        if not self.id_columns:
            logger.warning("No ID columns specified — skipping soft duplicate detection.")
            return 0

        available_ids = [c for c in self.id_columns if c in self.df.columns]
        if not available_ids:
            logger.warning(f"ID columns {self.id_columns} not found in dataset.")
            return 0

        # Group by ID columns to find groups with multiple records
        grouped = self.df.groupby(available_ids)
        total_flagged = 0

        for group_key, group_df in grouped:
            if len(group_df) <= 1:
                continue

            group_id = str(group_key)
            reason = self._classify_soft_duplicate(group_df)

            # Keep most recent as primary if timestamp available
            if self.timestamp_column and self.timestamp_column in group_df.columns:
                try:
                    sorted_group = group_df.sort_values(self.timestamp_column, ascending=False)
                    primary_idx = sorted_group.index[0]
                    secondary_idxs = sorted_group.index[1:]
                except Exception:
                    primary_idx = group_df.index[0]
                    secondary_idxs = group_df.index[1:]
            else:
                primary_idx = group_df.index[0]
                secondary_idxs = group_df.index[1:]

            self.df.loc[secondary_idxs, "__duplicate_status__"] = "SECONDARY"
            self.df.loc[secondary_idxs, "__duplicate_reason__"] = reason
            self.df.loc[group_df.index, "__duplicate_group_id__"] = group_id

            total_flagged += len(secondary_idxs)
            self._log_resolution(reason, len(secondary_idxs), group_id=group_id)

        if total_flagged > 0:
            logger.info(f"Soft duplicates flagged: {total_flagged}")

        return total_flagged

    def _classify_soft_duplicate(self, group_df: pd.DataFrame) -> str:
        """
        Classify why a soft duplicate exists.
        This helps downstream teams understand what happened.
        """
        if self.source_column and self.source_column in group_df.columns:
            sources = group_df[self.source_column].nunique()
            if sources > 1:
                return REASON_MULTI_VISIT  # Different workers/devices

        if self.timestamp_column and self.timestamp_column in group_df.columns:
            try:
                times = pd.to_datetime(group_df[self.timestamp_column])
                time_diff = (times.max() - times.min()).total_seconds()
                if time_diff < 300:  # Within 5 minutes — likely sync conflict
                    return REASON_SYNC_CONFLICT
                else:
                    return REASON_MULTI_VISIT  # Legitimate re-visit
            except Exception:
                pass

        return REASON_UNKNOWN

    def _log_resolution(self, reason: str, count: int, group_id: str = ""):
        self.resolution_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason,
            "records_flagged": count,
            "group_id": group_id,
        })

    def get_resolution_summary(self) -> Dict:
        """Return summary of all duplicate resolutions."""
        total_secondary = (self.df["__duplicate_status__"] == "SECONDARY").sum()
        by_reason = {}
        for entry in self.resolution_log:
            reason = entry["reason"]
            by_reason[reason] = by_reason.get(reason, 0) + entry["records_flagged"]

        return {
            "total_records": len(self.df),
            "primary_records": len(self.df) - int(total_secondary),
            "secondary_records": int(total_secondary),
            "by_reason": by_reason,
            "note": "Secondary records are preserved with flags — not deleted. Review before exclusion from analytics."
        }
