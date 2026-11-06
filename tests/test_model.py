import math

import pandas as pd
import pytest

from transition_risk import emissions, stress

CFG = {
    "study_years": [2030],
    "fuel_co2_kg_per_gj": {"Coal": 94.6, "Gas": 56.1},
    "efficiency": {
        "Coal": {"default": 0.37, "by_commissioning_year": [[1900, 1999, 0.33], [2000, 2100, 0.40]]},
        "Gas": 0.50,
    },
    "generation": {"column": "estimated_generation_gwh_2017", "capacity_factor_override": {}},
    "countries": {"CHN": {"name": "China", "currency": "CNY", "tariff_per_mwh": 400, "ebitda_margin": 0.15}},
    "scenarios": {"s": {"label": "s", "CHN": {"carbon_price": {2030: 200}, "uncovered_share": {2030: 0.5}}}},
    "flags": {"watch_fraction_of_margin": 0.5},
}


def _plants():
    return pd.DataFrame({
        "gppd_idnr": ["a", "b", "c", "d"],
        "name": ["Old coal", "New coal", "Gas", "Wind"],
        "country": "CHN", "province": "Test", "province_zh": "测试", "owner": None,
        "primary_fuel": ["Coal", "Coal", "Gas", "Wind"],
        "capacity_mw": [1000.0, 1000.0, 500.0, 100.0],
        "commissioning_year": [1990.0, 2015.0, float("nan"), 2018.0],
        "latitude": 30.0, "longitude": 120.0,
        "estimated_generation_gwh_2017": [5000.0, 5000.0, 2000.0, 250.0],
    })


def test_emission_factor_formula():
    # 94.6 kg/GJ x 3.6 GJ/MWh / 1000 / 0.40 = 0.8514 tCO2/MWh
    assert emissions.emission_factor("Coal", 0.40, CFG) == pytest.approx(0.8514)
    assert emissions.emission_factor("Wind", 0.40, CFG) == 0.0


def test_coal_efficiency_banding():
    assert emissions.plant_efficiency("Coal", 1990, CFG) == 0.33
    assert emissions.plant_efficiency("Coal", 2015, CFG) == 0.40
    assert emissions.plant_efficiency("Coal", float("nan"), CFG) == 0.37


def test_older_coal_emits_more_and_renewables_excluded():
    df = emissions.add_emissions(_plants(), CFG)
    old, new = df.loc[0, "emissions_tco2"], df.loc[1, "emissions_tco2"]
    assert old > new
    assert df.loc[3, "emissions_tco2"] == 0
    assert not df.loc[3, "is_fossil"]


def test_carbon_cost_and_flags():
    df = emissions.add_emissions(_plants(), CFG)
    res = stress.stress(df, CFG)
    assert set(res["gppd_idnr"]) == {"a", "b", "c"}  # wind not stressed
    new = res[res["gppd_idnr"] == "b"].iloc[0]
    expected_cost = 5_000_000 * 0.8514 * 200 * 0.5
    assert new["carbon_cost"] == pytest.approx(expected_cost)
    assert new["cost_share"] == pytest.approx(expected_cost / (5_000_000 * 400))
    # cost share 0.213 vs margin 0.15 -> High
    assert new["flag"] == "High"
    gas = res[res["gppd_idnr"] == "c"].iloc[0]
    # gas: 0.40392 x 200 x 0.5 / 400 = 0.101 -> 0.67 of margin -> Watch
    assert gas["flag"] == "Watch"
    assert math.isclose(gas["margin_used"], 0.10098 / 0.15, rel_tol=1e-3)
    # break-even effective price for new coal: 0.15 x 400 / 0.8514 = 70.47 CNY/t
    assert new["breakeven_price"] == pytest.approx(70.47, rel=1e-3)


def test_pass_through_reduces_absorbed_cost():
    cfg = {**CFG, "countries": {"CHN": {**CFG["countries"]["CHN"], "pass_through": 0.5}}}
    res = stress.stress(emissions.add_emissions(_plants(), cfg), cfg)
    new = res[res["gppd_idnr"] == "b"].iloc[0]
    assert new["net_carbon_cost"] == pytest.approx(new["carbon_cost"] * 0.5)
    assert new["flag"] == "Watch"  # 0.213 x 0.5 = 0.106 -> 0.71 of margin
