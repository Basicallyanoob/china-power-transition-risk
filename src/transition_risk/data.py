"""Download and load the public input datasets.

Sources (both downloaded from GitHub):
- WRI Global Power Plant Database v1.3.0, CC BY 4.0
  https://github.com/wri/global-power-plant-database
- Natural Earth 1:10m admin-1 states and provinces, public domain
  https://github.com/nvkelso/natural-earth-vector
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd

GPPD_URL = (
    "https://raw.githubusercontent.com/wri/global-power-plant-database/"
    "master/output_database/global_power_plant_database.csv"
)
ADMIN1_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_10m_admin_1_states_provinces.geojson"
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
GPPD_PATH = DATA_DIR / "global_power_plant_database.csv"
ADMIN1_PATH = DATA_DIR / "ne_10m_admin_1_states_provinces.geojson"

COUNTRIES = {"CHN": "CN", "IRL": "IE"}  # ISO3 (GPPD) -> ISO2 (Natural Earth)


def download(force: bool = False) -> None:
    """Fetch both datasets into ./data (skips files that already exist)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for url, path in [(GPPD_URL, GPPD_PATH), (ADMIN1_URL, ADMIN1_PATH)]:
        if path.exists() and not force:
            continue
        print(f"Downloading {url}")
        urllib.request.urlretrieve(url, path)


def load_plants(countries: list[str] | None = None) -> pd.DataFrame:
    """Load GPPD plants for the given ISO3 countries."""
    countries = countries or list(COUNTRIES)
    df = pd.read_csv(GPPD_PATH, low_memory=False)
    df = df[df["country"].isin(countries)].copy()
    keep = [
        "country", "country_long", "name", "gppd_idnr", "capacity_mw",
        "latitude", "longitude", "primary_fuel", "commissioning_year", "owner",
        "source", "estimated_generation_gwh_2017", "estimated_generation_note_2017",
    ]
    return df[keep].reset_index(drop=True)


def load_admin1(countries: list[str] | None = None) -> gpd.GeoDataFrame:
    """Load province/county boundaries for the given ISO3 countries."""
    countries = countries or list(COUNTRIES)
    iso2 = [COUNTRIES[c] for c in countries]
    gdf = gpd.read_file(ADMIN1_PATH, columns=["iso_a2", "name_en", "name_zh", "type_en"])
    gdf = gdf[gdf["iso_a2"].isin(iso2)].copy()
    return gdf.rename(columns={"name_en": "province", "name_zh": "province_zh"})
