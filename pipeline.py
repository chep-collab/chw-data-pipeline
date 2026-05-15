"""
pipeline.py
-----------
Orchestrates the full CHW data preparation pipeline.

Usage:
    python src/pipeline.py --input data/raw/chw_records.csv --country KE
    python src/pipeline.py --input data/raw/ --multi-country
"""

import argparse
import pandas as pd
import json
import os
from datetime import datetime
from pathlib import Path

from profiler import DataProfiler
from cleaner import CHWDataCleaner
from deduplicator import Deduplicator
from country_mapper import CountryMapper

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def run_pipeline(
    input_path: str,
    country_code: str,
    output_dir: str = "data/output",
    id_columns: list = None,
    timestamp_column: str = None,
) -> dict:
    """
    Run the full pipeline for a single country dataset.

    Returns a summary report.
    """
    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    logger.info(f"Pipeline started | Run ID: {run_id} | Country: {country_code}")

    # ── STEP 1: Load ─────────────────────────────────────────────────────
    logger.info("Step 1/5: Loading data...")
    df = pd.read_csv(input_path)
    original_row_count = len(df)
    logger.info(f"Loaded {original_row_count} rows from {input_path}")

    # ── STEP 2: Profile ───────────────────────────────────────────────────
    logger.info("Step 2/5: Profiling...")
    profiler = DataProfiler(df, country_code=country_code)
    profile = profiler.run()

    # ── STEP 3: Map country schema ────────────────────────────────────────
    logger.info("Step 3/5: Applying country schema mapping...")
    mapper = CountryMapper(country_code=country_code)
    df = mapper.apply(df)
    coverage = mapper.get_coverage_report()
    logger.info(f"Schema coverage: {coverage['coverage_rate']:.1%}")

    # ── STEP 4: Clean ─────────────────────────────────────────────────────
    logger.info("Step 4/5: Cleaning...")
    cleaner = CHWDataCleaner(df, country_code=country_code)
    df, audit_log = cleaner.run()

    # ── STEP 5: Deduplicate ───────────────────────────────────────────────
    logger.info("Step 5/5: Deduplicating...")
    id_cols = id_columns or ["household_id", "patient_id"]
    available_ids = [c for c in id_cols if c in df.columns]

    if available_ids:
        deduper = Deduplicator(
            df,
            id_columns=available_ids,
            timestamp_column=timestamp_column or "visit_date",
            source_column="data_source"
        )
        df = deduper.run()
        dupe_summary = deduper.get_resolution_summary()
    else:
        dupe_summary = {"note": "No ID columns found — deduplication skipped"}

    # ── OUTPUT ────────────────────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)

    output_file = os.path.join(output_dir, f"chw_cleaned_{country_code}_{run_id}.csv")
    df.to_csv(output_file, index=False)

    audit_file = os.path.join(output_dir, f"audit_log_{country_code}_{run_id}.csv")
    audit_log.to_dataframe().to_csv(audit_file, index=False)

    report = {
        "run_id": run_id,
        "country": country_code,
        "input_file": input_path,
        "output_file": output_file,
        "audit_log": audit_file,
        "original_rows": original_row_count,
        "output_rows": len(df),
        "completeness_score": profile["completeness_score"],
        "transformations_applied": len(audit_log.entries),
        "duplicate_summary": dupe_summary,
        "schema_coverage": coverage["coverage_rate"],
        "flags_generated": int((df.get("__data_quality_flags__", pd.Series([""])) != "").sum()),
        "completed_at": datetime.utcnow().isoformat(),
    }

    report_file = os.path.join(output_dir, f"pipeline_report_{country_code}_{run_id}.json")
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Pipeline complete | Output: {output_file} | Report: {report_file}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CHW Data Pipeline")
    parser.add_argument("--input", required=True, help="Path to input CSV file")
    parser.add_argument("--country", required=True, help="ISO country code (e.g. KE, ZM, LR)")
    parser.add_argument("--output-dir", default="data/output", help="Output directory")
    parser.add_argument("--id-columns", nargs="+", help="ID columns for deduplication")
    parser.add_argument("--timestamp-column", help="Timestamp column name")

    args = parser.parse_args()

    report = run_pipeline(
        input_path=args.input,
        country_code=args.country,
        output_dir=args.output_dir,
        id_columns=args.id_columns,
        timestamp_column=args.timestamp_column,
    )

    print("\n" + "="*60)
    print("PIPELINE SUMMARY")
    print("="*60)
    for key, value in report.items():
        print(f"{key}: {value}")
