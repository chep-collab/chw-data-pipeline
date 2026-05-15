"""
country_mapper.py
-----------------
Handles field name conflicts and schema differences
across multi-country CHW deployments.

The same data field often has different names in different
country deployments — sometimes due to different tools,
sometimes due to local language adaptations, sometimes
due to different programme designs.

This module maps country-specific schemas to a canonical schema
so downstream analytics can work on a consistent structure.
"""

import pandas as pd
import yaml
import json
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Canonical schema — the standard field names all countries map to
CANONICAL_SCHEMA = {
    "household_id": "Unique household identifier",
    "visit_date": "Date of CHW visit (ISO 8601)",
    "chw_id": "Community health worker ID",
    "patient_id": "Patient/beneficiary identifier",
    "age_years": "Patient age in years",
    "sex": "Patient sex (M/F/Other)",
    "visit_type": "Type of health visit",
    "outcome": "Visit outcome or diagnosis",
    "referral_made": "Whether referral was made (boolean)",
    "gps_lat": "GPS latitude",
    "gps_lon": "GPS longitude",
    "data_source": "Data collection tool/source",
    "sync_timestamp": "When record was synced to central system",
    "country_code": "ISO country code",
}

# Example country-specific mappings
# In production, these would be loaded from config files
# managed by the country implementation teams
DEFAULT_COUNTRY_MAPPINGS = {
    "KE": {  # Kenya
        "hh_id": "household_id",
        "visit_dt": "visit_date",
        "worker_id": "chw_id",
        "client_id": "patient_id",
        "age": "age_years",
        "gender": "sex",
        "visit_category": "visit_type",
        "result": "outcome",
        "referred": "referral_made",
        "latitude": "gps_lat",
        "longitude": "gps_lon",
    },
    "ZM": {  # Zambia
        "household_code": "household_id",
        "date_of_visit": "visit_date",
        "enumerator_id": "chw_id",
        "beneficiary_id": "patient_id",
        "age_at_visit": "age_years",
        "sex": "sex",
        "service_type": "visit_type",
        "service_outcome": "outcome",
        "referral_status": "referral_made",
        "gps_latitude": "gps_lat",
        "gps_longitude": "gps_lon",
    },
    "LR": {  # Liberia
        "hhold_id": "household_id",
        "visit_date": "visit_date",
        "chw_code": "chw_id",
        "patient_code": "patient_id",
        "pt_age": "age_years",
        "pt_sex": "sex",
        "visit_type": "visit_type",
        "visit_outcome": "outcome",
        "made_referral": "referral_made",
        "lat": "gps_lat",
        "lng": "gps_lon",
    },
    "MW": {  # Malawi
        "hh_identifier": "household_id",
        "service_date": "visit_date",
        "health_worker_id": "chw_id",
        "client_code": "patient_id",
        "client_age": "age_years",
        "client_sex": "sex",
        "service_category": "visit_type",
        "service_result": "outcome",
        "referral_yn": "referral_made",
        "coord_lat": "gps_lat",
        "coord_lon": "gps_lon",
    }
}


class CountryMapper:
    """
    Maps country-specific field names to the canonical schema.

    Design principle: the mapping is a collaboration between
    engineers and the country teams who know what the fields
    actually mean. We never assume — we document and verify.
    """

    def __init__(
        self,
        country_code: str,
        custom_mapping: Optional[Dict] = None,
        config_path: Optional[str] = None
    ):
        self.country_code = country_code.upper()
        self.mapping = self._load_mapping(custom_mapping, config_path)
        self.unmapped_fields = []

    def _load_mapping(self, custom_mapping, config_path) -> Dict:
        """Load mapping from custom dict, config file, or defaults."""
        if custom_mapping:
            logger.info(f"Using custom mapping for {self.country_code}")
            return custom_mapping

        if config_path:
            try:
                with open(config_path, "r") as f:
                    all_mappings = yaml.safe_load(f)
                    if self.country_code in all_mappings:
                        logger.info(f"Loaded mapping from config: {config_path}")
                        return all_mappings[self.country_code]
            except Exception as e:
                logger.warning(f"Could not load config from {config_path}: {e}")

        if self.country_code in DEFAULT_COUNTRY_MAPPINGS:
            logger.info(f"Using default mapping for {self.country_code}")
            return DEFAULT_COUNTRY_MAPPINGS[self.country_code]

        logger.warning(f"No mapping found for country: {self.country_code}. Columns will be passed through unchanged.")
        return {}

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply the country mapping to a dataframe.
        Returns dataframe with canonical column names.
        Fields not in the mapping are preserved with their original names.
        """
        if not self.mapping:
            return df

        df_mapped = df.copy()
        rename_dict = {}
        self.unmapped_fields = []

        for col in df.columns:
            col_lower = col.lower().strip()
            if col_lower in self.mapping:
                canonical = self.mapping[col_lower]
                rename_dict[col] = canonical
                logger.debug(f"Mapped: {col} → {canonical}")
            else:
                self.unmapped_fields.append(col)

        if rename_dict:
            df_mapped.rename(columns=rename_dict, inplace=True)

        if self.unmapped_fields:
            logger.info(
                f"Fields not in mapping (passed through): {self.unmapped_fields}"
            )

        # Add country code column
        df_mapped["country_code"] = self.country_code

        logger.info(
            f"Mapping applied | Country: {self.country_code} | "
            f"Mapped: {len(rename_dict)} fields | "
            f"Unmapped: {len(self.unmapped_fields)} fields"
        )

        return df_mapped

    def get_coverage_report(self) -> Dict:
        """Report on how well the mapping covers the canonical schema."""
        canonical_fields = set(CANONICAL_SCHEMA.keys())
        mapped_targets = set(self.mapping.values())
        covered = canonical_fields & mapped_targets
        missing = canonical_fields - mapped_targets

        return {
            "country": self.country_code,
            "canonical_fields": len(canonical_fields),
            "fields_covered": len(covered),
            "fields_missing": list(missing),
            "coverage_rate": round(len(covered) / len(canonical_fields), 3),
            "note": "Missing fields may not be collected in this country's programme — verify with country team before treating as a gap."
        }
