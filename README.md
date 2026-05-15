# Community Health Worker Data Pipeline
### AI-Ready Data Preparation for Multi-Country CHW Reporting Systems

A production-grade data pipeline for cleaning, standardising, and preparing community health worker (CHW) reporting data for AI-driven analytics workflows. Built to handle real-world data quality challenges across multi-country deployments in low-resource environments.

---

## The Problem This Solves

Community health worker data collected across multiple country deployments is notoriously messy:
- Missing values from interrupted mobile data collection
- Inconsistent date formats across different country configurations
- Duplicate records from offline sync conflicts
- Fields that mean different things in different country contexts
- Variable data quality from field teams with different training levels

This pipeline handles all of the above — with a full audit trail so every transformation is documented and reversible.

---

## What This Pipeline Does

```
Raw CHW Data (CSV/JSON) 
    → Audit & Profile
    → Standardise & Validate  
    → Deduplicate (with lineage)
    → Flag for Human Review
    → AI-Ready Output + Audit Log
```

---

## Key Features

- **Multi-country schema mapping** — handles field-name conflicts across country deployments
- **Intelligent date parsing** — detects and standardises multiple date formats without assumptions
- **Duplicate resolution** — timestamp + source ID strategy, never silent drops
- **Missing value handling** — flags and documents rather than imputes blindly
- **Full audit trail** — every transformation logged with reason codes
- **Offline-safe** — designed for data collected in zero-connectivity environments

---

## Tech Stack

- Python 3.10+
- Pandas, NumPy
- Great Expectations (data quality)
- SQLite / PostgreSQL
- Docker

---

## Project Structure

```
chw-data-pipeline/
├── data/
│   ├── sample_raw/          # Sample raw CHW datasets (anonymised)
│   └── sample_output/       # Example cleaned output
├── src/
│   ├── profiler.py          # Dataset auditing and profiling
│   ├── cleaner.py           # Core cleaning transformations
│   ├── deduplicator.py      # Duplicate detection and resolution
│   ├── validator.py         # Schema and business rule validation
│   ├── country_mapper.py    # Multi-country field mapping
│   └── pipeline.py          # Orchestration
├── tests/
│   ├── test_cleaner.py
│   ├── test_deduplicator.py
│   └── test_validator.py
├── docs/
│   ├── ARCHITECTURE.md      # System design decisions
│   ├── DATA_DICTIONARY.md   # Field definitions by country
│   └── AUDIT_LOG_SCHEMA.md  # Audit trail documentation
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Quick Start

```bash
git clone https://github.com/mercychepngeno/chw-data-pipeline
cd chw-data-pipeline
pip install -r requirements.txt

# Run the full pipeline on sample data
python src/pipeline.py --input data/sample_raw/chw_records.csv --country KE

# Run with multiple country files
python src/pipeline.py --input data/sample_raw/ --multi-country --config config/country_schemas.yaml
```

---

## Design Decisions

### Why flag missing values rather than impute?
In health data, imputed values can introduce systematic bias that affects care decisions for specific populations. We flag and document missing values so that downstream AI models can handle them explicitly, with full knowledge of the data gaps.

### Why timestamp + source ID for deduplication?
Duplicate records in CHW systems often arise from legitimate causes — two health workers visiting the same household, sync conflicts from offline collection. Silent drops lose information. Our strategy preserves both records with a resolution flag and reason code.

### Why a full audit trail?
In systems that inform clinical and community health decisions, data lineage is not optional. Every transformation is logged: what changed, when, why, and what was flagged for human review.

---

## Real-World Context

This pipeline reflects patterns from a community registry deployment covering 250,000+ households in Zambia — one of the largest community-level data infrastructure projects in the region — where offline data collection, sync conflicts, and multi-team field operations created exactly these data quality challenges.

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Contributing

This project is designed to be adapted for different CHW programme contexts. See `docs/ARCHITECTURE.md` for guidance on adding new country schemas or extending the validation rules.

---

*Built with a focus on data integrity for health systems that serve the world's most remote communities.*
