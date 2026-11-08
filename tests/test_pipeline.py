"""End-to-end check: run the whole pipeline on a 20-plant sample and check its outputs.

The sample plants and boundary boxes below are made up (SYNTHETIC test fixtures, not
data). They only need the same columns as the real inputs, so the test runs in a
second without downloading anything. The model settings come from the real
config/assumptions.yaml, so the test also catches a config change that breaks the
pipeline.

If a test here fails after you change the code on purpose (for example you add an
output column), update the expected values below in the same commit.
"""
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
import yaml
from shapely.geometry import box

from transition_risk.__main__ import run

ROOT = Path(__file__).resolve().parents[1]
NAN = float("nan")

# (country, fuel, province box, longitude, latitude, commissioning year, owner, 2017 GWh)
SAMPLE = [
    ("CHN", "Coal", "Alpha", 111.0, 31.0, 1995, "Owner A", 5000),
    ("CHN", "Coal", "Alpha", 110.5, 30.5, 2005, "Owner A", 4000),
    ("CHN", "Coal", "Alpha", 111.5, 31.5, 2012, "Owner B", 6000),
    ("CHN", "Coal", "Alpha", 110.2, 31.8, 2018, "Owner B", 3000),
    ("CHN", "Coal", "Alpha", 111.8, 30.2, NAN, None, 2000),         # no commissioning year
    ("CHN", "Coal", "Alpha", 110.8, 31.2, 1985, "Owner C", 1500),
    ("CHN", "Coal", "Beta", 113.0, 31.0, 2008, "Owner A", 5500),
    ("CHN", "Coal", "Beta", 112.5, 30.5, 2015, "Owner B", 4500),
    ("CHN", "Coal", "Beta", 113.5, 31.5, 1998, "Owner C", 2500),
    ("CHN", "Coal", "Beta", 112.2, 31.8, 2011, "Owner A", 3500),
    ("CHN", "Coal", "Beta", 114.08, 31.0, 2016, "Owner B", 4000),   # ~8 km offshore: snaps to Beta
    ("CHN", "Gas", "Alpha", 111.2, 30.8, 2010, "Owner C", 1200),
    ("CHN", "Gas", "Beta", 113.2, 30.8, 2019, "Owner C", NAN),      # no generation: not stressed
    ("CHN", "Oil", "Beta", 112.8, 31.2, 1990, "Owner A", 300),
    ("CHN", "Solar", "Alpha", 111.6, 30.6, 2017, "Owner D", 150),
    ("CHN", "Wind", "Beta", 113.6, 30.4, 2016, "Owner D", 250),
    ("IRL", "Coal", "Gamma", -8.0, 53.0, 1987, "Owner E", 4000),
    ("IRL", "Gas", "Gamma", -8.5, 52.5, 2002, "Owner E", 2500),
    ("IRL", "Oil", "Gamma", -7.5, 53.5, 1978, "Owner E", 100),
    ("IRL", "Wind", "Gamma", -8.2, 53.8, 2012, "Owner F", 200),
]

# Expected columns of every output file. A change here is a change to the outputs.
EXPECTED_COLUMNS = {
    "fleet_summary.csv": ["country", "primary_fuel", "plants", "capacity_gw", "emissions_mtco2"],
    "scenario_paths.csv": [
        "country", "currency", "scenario", "year", "carbon_cost_bn", "high_capacity_gw",
        "fossil_capacity_gw", "high_share_of_fossil_capacity",
    ],
    "province_exposure.csv": [
        "province", "province_zh", "fossil_plants", "fossil_capacity_gw", "emissions_mtco2",
        "carbon_cost_cny_bn", "net_carbon_cost_cny_bn", "high_flag_capacity_gw", "share_high_flag",
    ],
    "owner_exposure.csv": ["owner", "plants", "capacity_gw", "carbon_cost_cny_bn"],
    "plant_watchlist_top50.csv": [
        "gppd_idnr", "name", "province", "province_zh", "owner", "primary_fuel", "capacity_mw",
        "commissioning_year", "ef_tco2_mwh", "cost_share", "margin_used",
        "breakeven_effective_price_cny_t", "flag", "emissions_mtco2", "carbon_cost_cny_m",
        "net_carbon_cost_cny_m",
    ],
    "breakeven_by_vintage.csv": [
        "country", "currency", "primary_fuel", "ef_tco2_mwh", "plants", "capacity_gw",
        "breakeven_effective_price",
    ],
    "breakeven_sensitivity.csv": [
        "country", "currency", "primary_fuel", "ebitda_margin", "pass_through", "is_base_case",
        "breakeven_least_efficient", "breakeven_capacity_weighted", "breakeven_most_efficient",
    ],
}

# Expected row counts for the sample, worked out by hand:
#   fossil plants with generation: 13 in China (11 coal, 1 gas, 1 oil) + 3 in Ireland = 16
#   fleet_summary:   China Coal/Gas/Oil/Solar/Wind + Ireland Coal/Gas/Oil/Wind = 9 rows
#   scenario_paths:  2 countries x 3 scenarios x 4 study years = 24 rows
#   province:        Alpha and Beta = 2 rows (the offshore plant joins Beta)
#   owners:          Owner A, B, C and "Owner not reported" (solar Owner D is not fossil) = 4 rows
#   watchlist:       all 13 Chinese fossil plants (fewer than 50)
#   break-even:      China coal 3 efficiency bands + gas + oil, Ireland coal + gas + oil = 8 rows
#   sensitivity:     3 EBITDA margins x 3 pass-through rates in the config grid = 9 rows
EXPECTED_ROWS = {
    "fleet_summary.csv": 9,
    "scenario_paths.csv": 24,
    "province_exposure.csv": 2,
    "owner_exposure.csv": 4,
    "plant_watchlist_top50.csv": 13,
    "breakeven_by_vintage.csv": 8,
    "breakeven_sensitivity.csv": 9,
}

FIGURES = [
    "flagged_capacity_by_scenario.png", "breakeven_vs_scenarios.png", "province_carbon_cost.png",
    "breakeven_sensitivity.png",
]


def _sample_plants() -> pd.DataFrame:
    """20 synthetic plants with the same columns as data.load_plants()."""
    cols = ["country", "primary_fuel", "_box", "longitude", "latitude",
            "commissioning_year", "owner", "estimated_generation_gwh_2017"]
    df = pd.DataFrame(SAMPLE, columns=cols).drop(columns="_box")
    df["country_long"] = df["country"].map({"CHN": "China", "IRL": "Ireland"})
    df["name"] = [f"Sample plant {i + 1}" for i in range(len(df))]
    df["gppd_idnr"] = [f"TEST{i + 1:03d}" for i in range(len(df))]
    df["capacity_mw"] = df["estimated_generation_gwh_2017"].fillna(1000) / 8.76 / 0.5  # ~50% CF
    df["source"] = "synthetic"
    df["estimated_generation_note_2017"] = "synthetic"
    return df


def _sample_admin1() -> gpd.GeoDataFrame:
    """Three rectangular test areas: two Chinese provinces and one Irish county."""
    return gpd.GeoDataFrame(
        {
            "iso_a2": ["CN", "CN", "IE"],
            "province": ["Alpha", "Beta", "Gamma"],
            "province_zh": ["甲省", "乙省", "丙郡"],
            "type_en": ["Province", "Province", "County"],
        },
        geometry=[box(110, 30, 112, 32), box(112, 30, 114, 32), box(-9, 52, -7, 54)],
        crs="EPSG:4326",
    )


@pytest.fixture(scope="module")
def outputs(tmp_path_factory):
    cfg = yaml.safe_load((ROOT / "config" / "assumptions.yaml").read_text(encoding="utf-8"))
    out = tmp_path_factory.mktemp("outputs")
    summary = run(_sample_plants(), _sample_admin1(), cfg, out)
    return out, summary


def test_sample_has_20_plants():
    assert len(_sample_plants()) == 20


def test_run_summary(outputs):
    out, summary = outputs
    assert summary["plants_loaded"] == 20
    assert summary["unassigned_province"] == 0
    assert summary["fossil_plants_stressed"] == 16
    assert json.loads((out / "run_summary.json").read_text()) == summary


@pytest.mark.parametrize("filename", sorted(EXPECTED_COLUMNS))
def test_csv_columns_and_rows(outputs, filename):
    out, _ = outputs
    df = pd.read_csv(out / filename, encoding="utf-8-sig")
    assert list(df.columns) == EXPECTED_COLUMNS[filename]
    assert len(df) == EXPECTED_ROWS[filename]


def test_offshore_plant_snaps_to_nearest_province(outputs):
    out, _ = outputs
    prov = pd.read_csv(out / "province_exposure.csv", encoding="utf-8-sig")
    assert dict(zip(prov["province"], prov["fossil_plants"])) == {"Alpha": 7, "Beta": 6}


@pytest.mark.parametrize("filename", FIGURES)
def test_figures_written(outputs, filename):
    path = outputs[0] / "figures" / filename
    assert path.exists() and path.stat().st_size > 10_000
