"""
app.py
------
Streamlit UI for the CHW Data Pipeline.
Upload a CSV, select a country, run the full pipeline,
and download cleaned outputs with audit logs.
"""

import streamlit as st
import pandas as pd
import io
import json
import sys
import os
from datetime import datetime

# Add src/ to path so imports work whether files are in root or src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.dirname(__file__))

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CHW Data Pipeline",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }

    .stApp {
        background-color: #0f1117;
        color: #e8e8e8;
    }

    h1, h2, h3 {
        font-family: 'IBM Plex Mono', monospace !important;
        color: #00d4a8 !important;
    }

    .metric-card {
        background: #1a1d27;
        border: 1px solid #2a2d3a;
        border-left: 3px solid #00d4a8;
        border-radius: 4px;
        padding: 16px 20px;
        margin-bottom: 12px;
    }

    .metric-value {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 2rem;
        font-weight: 600;
        color: #00d4a8;
    }

    .metric-label {
        font-size: 0.78rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }

    .flag-warning {
        background: #1f1a0f;
        border-left: 3px solid #f5a623;
        padding: 10px 14px;
        border-radius: 3px;
        margin: 6px 0;
        font-size: 0.88rem;
        color: #f5c842;
    }

    .flag-info {
        background: #0f1a1f;
        border-left: 3px solid #4aa8d8;
        padding: 10px 14px;
        border-radius: 3px;
        margin: 6px 0;
        font-size: 0.88rem;
        color: #7ac8f0;
    }

    .step-badge {
        display: inline-block;
        background: #00d4a8;
        color: #0f1117;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.7rem;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 2px;
        margin-right: 8px;
    }

    .stButton > button {
        background: #00d4a8 !important;
        color: #0f1117 !important;
        font-family: 'IBM Plex Mono', monospace !important;
        font-weight: 600 !important;
        border: none !important;
        border-radius: 3px !important;
        padding: 10px 24px !important;
        letter-spacing: 0.05em;
    }

    .stButton > button:hover {
        background: #00b891 !important;
    }

    .stDownloadButton > button {
        background: #1a1d27 !important;
        color: #00d4a8 !important;
        border: 1px solid #00d4a8 !important;
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.85rem !important;
        border-radius: 3px !important;
    }

    .stSelectbox label, .stFileUploader label {
        color: #aaa !important;
        font-size: 0.85rem !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }

    .stDataFrame {
        border: 1px solid #2a2d3a !important;
    }

    .sidebar .sidebar-content {
        background: #13151f;
    }

    hr {
        border-color: #2a2d3a !important;
    }

    .stAlert {
        border-radius: 3px !important;
    }

    .country-pill {
        display: inline-block;
        background: #1a1d27;
        border: 1px solid #2a2d3a;
        color: #00d4a8;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.75rem;
        padding: 3px 10px;
        border-radius: 20px;
        margin: 2px;
    }
</style>
""", unsafe_allow_html=True)


# ── Helpers ──────────────────────────────────────────────────────────────────
def import_pipeline_modules():
    """Dynamically import pipeline modules with helpful error messages."""
    modules = {}
    try:
        from profiler import DataProfiler
        modules["DataProfiler"] = DataProfiler
    except ImportError as e:
        st.error(f"Could not import profiler.py: {e}")

    try:
        from cleaner import CHWDataCleaner
        modules["CHWDataCleaner"] = CHWDataCleaner
    except ImportError as e:
        st.error(f"Could not import cleaner.py: {e}")

    try:
        from deduplicator import Deduplicator
        modules["Deduplicator"] = Deduplicator
    except ImportError as e:
        st.error(f"Could not import deduplicator.py: {e}")

    try:
        from country_mapper import CountryMapper
        modules["CountryMapper"] = CountryMapper
    except ImportError as e:
        st.error(f"Could not import country_mapper.py: {e}")

    return modules


def run_full_pipeline(df, country_code, modules):
    """Run the full pipeline and return results dict."""
    results = {}
    progress = st.progress(0)
    status = st.empty()

    # Step 1: Profile
    status.markdown('<span class="step-badge">01</span> Profiling data...', unsafe_allow_html=True)
    profiler = modules["DataProfiler"](df, country_code=country_code)
    profile = profiler.run()
    results["profile"] = profile
    progress.progress(20)

    # Step 2: Map country schema
    status.markdown('<span class="step-badge">02</span> Applying country schema mapping...', unsafe_allow_html=True)
    mapper = modules["CountryMapper"](country_code=country_code)
    df_mapped = mapper.apply(df)
    results["coverage"] = mapper.get_coverage_report()
    results["unmapped_fields"] = mapper.unmapped_fields
    progress.progress(40)

    # Step 3: Clean
    status.markdown('<span class="step-badge">03</span> Cleaning data...', unsafe_allow_html=True)
    cleaner = modules["CHWDataCleaner"](df_mapped, country_code=country_code)
    df_clean, audit_log = cleaner.run()
    results["audit_log"] = audit_log
    progress.progress(65)

    # Step 4: Deduplicate
    status.markdown('<span class="step-badge">04</span> Detecting duplicates...', unsafe_allow_html=True)
    id_cols = ["household_id", "patient_id"]
    available_ids = [c for c in id_cols if c in df_clean.columns]
    if available_ids:
        deduper = modules["Deduplicator"](
            df_clean,
            id_columns=available_ids,
            timestamp_column="visit_date",
            source_column="data_source"
        )
        df_final = deduper.run()
        results["dupe_summary"] = deduper.get_resolution_summary()
    else:
        df_final = df_clean
        results["dupe_summary"] = {"note": "No standard ID columns found — deduplication skipped."}
    progress.progress(90)

    results["df_final"] = df_final
    progress.progress(100)
    status.markdown('<span class="step-badge">✓</span> Pipeline complete!', unsafe_allow_html=True)

    return results


def df_to_csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8")


def dict_to_json_bytes(d):
    return json.dumps(d, indent=2, default=str).encode("utf-8")


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏥 CHW Pipeline")
    st.markdown("*Community Health Worker Data Preparation*")
    st.markdown("---")

    st.markdown("**Supported Countries**")
    for code, name in [("KE", "Kenya"), ("ZM", "Zambia"), ("LR", "Liberia"), ("MW", "Malawi")]:
        st.markdown(f'<span class="country-pill">{code}</span> {name}', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**Pipeline Steps**")
    steps = ["01 · Profile", "02 · Map Schema", "03 · Clean", "04 · Deduplicate"]
    for s in steps:
        st.markdown(f"`{s}`")

    st.markdown("---")
    st.markdown("**Design Principles**")
    st.caption("✓ Flag, don't impute\n✓ Document everything\n✓ Preserve duplicates\n✓ Audit every transform")


# ── Main ─────────────────────────────────────────────────────────────────────
st.markdown("# CHW Data Pipeline")
st.markdown("*AI-ready data preparation for Community Health Worker reporting data across multi-country deployments.*")
st.markdown("---")

# ── Upload & Config ───────────────────────────────────────────────────────────
col1, col2 = st.columns([2, 1])

with col1:
    uploaded_file = st.file_uploader(
        "Upload CHW Dataset (CSV)",
        type=["csv"],
        help="Upload a raw CHW reporting CSV file"
    )

with col2:
    country_code = st.selectbox(
        "Country",
        options=["KE", "ZM", "LR", "MW", "UNKNOWN"],
        format_func=lambda x: {
            "KE": "🇰🇪 Kenya",
            "ZM": "🇿🇲 Zambia",
            "LR": "🇱🇷 Liberia",
            "MW": "🇲🇼 Malawi",
            "UNKNOWN": "🌍 Unknown / Other"
        }.get(x, x)
    )

# ── Demo data option ──────────────────────────────────────────────────────────
if not uploaded_file:
    st.info("No file uploaded. You can run the pipeline on demo data to explore the tool.")
    use_demo = st.button("▶ Run with Demo Data")

    if use_demo:
        # Generate synthetic CHW demo data
        import numpy as np
        np.random.seed(42)
        n = 120
        demo_df = pd.DataFrame({
            "hh_id": [f"HH{str(i).zfill(4)}" for i in range(n)],
            "client_id": [f"P{str(i).zfill(5)}" for i in range(n)],
            "worker_id": [f"CHW{str(i % 12).zfill(3)}" for i in range(n)],
            "visit_dt": pd.date_range("2024-01-01", periods=n, freq="2D").strftime("%d/%m/%Y").tolist(),
            "age": np.random.choice([str(x) for x in range(1, 80)] + ["N/A", None, "unknown"], n),
            "gender": np.random.choice(["M", "F", "male", "female", None], n),
            "visit_category": np.random.choice(["ANC", "Immunisation", "MNCH", "Nutrition", None], n),
            "result": np.random.choice(["Healthy", "Referred", "Follow-up", "Treated", None], n),
            "referred": np.random.choice(["Yes", "No", "1", "0", None], n),
            "latitude": np.random.uniform(-1.5, 1.5, n).round(6).tolist(),
            "longitude": np.random.uniform(36.5, 37.5, n).round(6).tolist(),
        })
        # Add some duplicates
        demo_df = pd.concat([demo_df, demo_df.sample(8, random_state=1)], ignore_index=True)
        uploaded_file = None
        df_input = demo_df
        st.success(f"Demo dataset loaded: {len(df_input)} rows, {len(df_input.columns)} columns")
        run_pipeline_flag = True
    else:
        run_pipeline_flag = False
        df_input = None
else:
    df_input = pd.read_csv(uploaded_file)
    st.success(f"File loaded: **{uploaded_file.name}** — {len(df_input):,} rows, {len(df_input.columns)} columns")

    st.markdown("**Preview (first 5 rows)**")
    st.dataframe(df_input.head(), use_container_width=True)

    run_pipeline_flag = st.button("▶ Run Full Pipeline")

# ── Run Pipeline ──────────────────────────────────────────────────────────────
if run_pipeline_flag and df_input is not None:
    st.markdown("---")
    st.markdown("## Running Pipeline")

    modules = import_pipeline_modules()

    if len(modules) < 4:
        st.error("Some pipeline modules could not be loaded. Make sure cleaner.py, profiler.py, deduplicator.py, and country_mapper.py are in the same directory as app.py (or in src/).")
    else:
        try:
            results = run_full_pipeline(df_input, country_code, modules)

            st.markdown("---")
            st.markdown("## Results")

            # ── Key Metrics ───────────────────────────────────────────────────
            profile = results["profile"]
            audit = results["audit_log"]
            dupe = results["dupe_summary"]
            df_final = results["df_final"]

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-value">{profile['row_count']:,}</div>
                    <div class="metric-label">Total Records</div>
                </div>""", unsafe_allow_html=True)
            with m2:
                score = profile['completeness_score']
                color = "#00d4a8" if score >= 0.8 else "#f5a623" if score >= 0.6 else "#e05252"
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-value" style="color:{color}">{score:.1%}</div>
                    <div class="metric-label">Completeness Score</div>
                </div>""", unsafe_allow_html=True)
            with m3:
                transforms = len(audit.entries)
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-value">{transforms}</div>
                    <div class="metric-label">Transformations Applied</div>
                </div>""", unsafe_allow_html=True)
            with m4:
                dupes = dupe.get("secondary_records", 0)
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-value">{dupes}</div>
                    <div class="metric-label">Duplicates Flagged</div>
                </div>""", unsafe_allow_html=True)

            # ── Tabs ──────────────────────────────────────────────────────────
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📊 Data Quality Flags",
                "🗺 Schema Coverage",
                "🔁 Duplicates",
                "📋 Audit Log",
                "⬇ Downloads"
            ])

            with tab1:
                st.markdown("### Data Quality Flags")
                flags = profile.get("flags", [])
                if flags:
                    for flag in flags:
                        level = flag.get("level", "INFO")
                        css_class = "flag-warning" if level == "WARNING" else "flag-info"
                        icon = "⚠️" if level == "WARNING" else "ℹ️"
                        st.markdown(
                            f'<div class="{css_class}">{icon} {flag["message"]}</div>',
                            unsafe_allow_html=True
                        )
                else:
                    st.success("No quality flags raised.")

                st.markdown("### Column Profiles")
                col_data = []
                for col, info in profile.get("columns", {}).items():
                    col_data.append({
                        "Column": col,
                        "Type": info["dtype"],
                        "Null Count": info["null_count"],
                        "Null Rate": f"{info['null_rate']:.1%}",
                        "Unique Values": info["unique_values"],
                        "Warning": info.get("warning", "—")
                    })
                if col_data:
                    st.dataframe(pd.DataFrame(col_data), use_container_width=True)

            with tab2:
                st.markdown("### Schema Coverage Report")
                coverage = results.get("coverage", {})
                c1, c2 = st.columns(2)
                with c1:
                    rate = coverage.get("coverage_rate", 0)
                    st.metric("Coverage Rate", f"{rate:.1%}")
                    st.metric("Fields Covered", coverage.get("fields_covered", "—"))
                with c2:
                    missing = coverage.get("fields_missing", [])
                    st.markdown(f"**Missing Canonical Fields:** {len(missing)}")
                    if missing:
                        for f in missing:
                            st.markdown(f"- `{f}`")
                    else:
                        st.success("All canonical fields mapped!")

                unmapped = results.get("unmapped_fields", [])
                if unmapped:
                    st.markdown(f"**Fields passed through without mapping:** {len(unmapped)}")
                    st.code(", ".join(unmapped))

                if coverage.get("note"):
                    st.caption(coverage["note"])

            with tab3:
                st.markdown("### Duplicate Detection Summary")
                st.json(dupe)

                if "__duplicate_status__" in df_final.columns:
                    dupe_counts = df_final["__duplicate_status__"].value_counts()
                    st.bar_chart(dupe_counts)

            with tab4:
                st.markdown("### Audit Log")
                st.caption("Every transformation applied to your data, with reason codes.")
                audit_df = audit.to_dataframe()
                if not audit_df.empty:
                    st.dataframe(audit_df, use_container_width=True)
                    summary = audit.summary()
                    st.markdown(f"**Total:** {summary['total_transformations']} transformations across {len(summary['fields_touched'])} fields")
                else:
                    st.info("No transformations were logged.")

            with tab5:
                st.markdown("### Download Outputs")
                run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

                dl1, dl2, dl3 = st.columns(3)
                with dl1:
                    st.download_button(
                        label="⬇ Cleaned CSV",
                        data=df_to_csv_bytes(df_final),
                        file_name=f"chw_cleaned_{country_code}_{run_id}.csv",
                        mime="text/csv"
                    )
                with dl2:
                    audit_df = audit.to_dataframe()
                    st.download_button(
                        label="⬇ Audit Log CSV",
                        data=df_to_csv_bytes(audit_df),
                        file_name=f"audit_log_{country_code}_{run_id}.csv",
                        mime="text/csv"
                    )
                with dl3:
                    report = {
                        "run_id": run_id,
                        "country": country_code,
                        "original_rows": profile["row_count"],
                        "output_rows": len(df_final),
                        "completeness_score": profile["completeness_score"],
                        "transformations_applied": len(audit.entries),
                        "duplicate_summary": dupe,
                        "schema_coverage": results.get("coverage", {}).get("coverage_rate"),
                        "flags": profile.get("flags", []),
                        "completed_at": datetime.utcnow().isoformat(),
                    }
                    st.download_button(
                        label="⬇ Pipeline Report JSON",
                        data=dict_to_json_bytes(report),
                        file_name=f"pipeline_report_{country_code}_{run_id}.json",
                        mime="application/json"
                    )

                st.markdown("---")
                st.markdown("**Cleaned Data Preview**")
                st.dataframe(df_final.head(20), use_container_width=True)

        except Exception as e:
            st.error(f"Pipeline error: {e}")
            st.exception(e)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption("CHW Data Pipeline · Built for multi-country health data infrastructure · Audit-first design")
