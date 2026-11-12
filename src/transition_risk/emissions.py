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


def _check_capacity_factor(cf: float, where: str) -> None:
    """A capacity factor is a share of the year at full output, so it must be in (0, 1]."""
    if not 0 < cf <= 1:
        raise ValueError(f"capacity factor for {where} must be above 0 and at most 1, got {cf}")


def add_emissions(plants: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Add generation_mwh, efficiency, ef_tco2_mwh and emissions_tco2 columns.

    Generation comes from the GPPD column in the config unless a capacity factor
    override applies. Most specific wins: a province override for that fuel, then a
    fuel-wide override, then the GPPD estimate.
    """
    df = plants.copy()
    gen_cfg = cfg["generation"]
    df["generation_mwh"] = df[gen_cfg["column"]] * 1000
    for fuel, cf in (gen_cfg.get("capacity_factor_override") or {}).items():
        _check_capacity_factor(cf, fuel)
        mask = df["primary_fuel"] == fuel
        df.loc[mask, "generation_mwh"] = df.loc[mask, "capacity_mw"] * 8760 * cf

    by_province = gen_cfg.get("capacity_factor_by_province") or {}
    if by_province:
        if "province" not in df.columns:
            raise ValueError("capacity_factor_by_province needs plants with a province column "
                             "(run geo.assign_provinces first)")
        known = set(df["province"])
        for fuel, provinces in by_province.items():
            # A misspelt province would otherwise match no plants and change nothing silently.
            unknown = sorted(set(provinces) - known)
            if unknown:
                raise ValueError(f"capacity_factor_by_province.{fuel}: no plants in {unknown}; "
                                 "use the English names in outputs/province_exposure.csv")
            for province, cf in provinces.items():
                _check_capacity_factor(cf, f"{fuel} in {province}")
                mask = (df["primary_fuel"] == fuel) & (df["province"] == province)
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
