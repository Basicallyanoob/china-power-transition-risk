"""Estimate plant-level generation and CO2 emissions from transparent assumptions."""
from __future__ import annotations

import numpy as np
import pandas as pd

GJ_PER_MWH = 3.6


def plant_efficiency(fuel: str, commissioning_year: float, cfg: dict) -> float:
    """Net efficiency for a plant, banded by commissioning year for coal."""
    eff = cfg["efficiency"].get(fuel)
    if eff is None:
        return np.nan
    if isinstance(eff, (int, float)):
        return float(eff)
    if commissioning_year is not None and not np.isnan(commissioning_year):
        for first, last, value in eff["by_commissioning_year"]:
            if first <= commissioning_year <= last:
                return float(value)
    return float(eff["default"])


def emission_factor(fuel: str, efficiency: float, cfg: dict) -> float:
    """tCO2 per MWh of electricity = kgCO2/GJ x 3.6 / 1000 / efficiency."""
    kg_per_gj = cfg["fuel_co2_kg_per_gj"].get(fuel)
    if kg_per_gj is None or not efficiency or np.isnan(efficiency):
        return 0.0
    return kg_per_gj * GJ_PER_MWH / 1000 / efficiency


def add_emissions(plants: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Add generation_mwh, efficiency, ef_tco2_mwh and emissions_tco2 columns."""
    df = plants.copy()
    gen_cfg = cfg["generation"]
    df["generation_mwh"] = df[gen_cfg["column"]] * 1000
    for fuel, cf in (gen_cfg.get("capacity_factor_override") or {}).items():
        mask = df["primary_fuel"] == fuel
        df.loc[mask, "generation_mwh"] = df.loc[mask, "capacity_mw"] * 8760 * cf
    df["generation_mwh"] = df["generation_mwh"].fillna(0.0)

    df["efficiency"] = [
        plant_efficiency(f, y, cfg) for f, y in zip(df["primary_fuel"], df["commissioning_year"])
    ]
    df["ef_tco2_mwh"] = [
        emission_factor(f, e, cfg) for f, e in zip(df["primary_fuel"], df["efficiency"])
    ]
    df["emissions_tco2"] = df["generation_mwh"] * df["ef_tco2_mwh"]
    df["is_fossil"] = df["primary_fuel"].isin(cfg["fuel_co2_kg_per_gj"].keys())
    return df
