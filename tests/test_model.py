import math

import pandas as pd
import pytest

from transition_risk import emissions, report, stress

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


def test_breakeven_price_formula():
    # 0.15 x 400 / 0.8514 = 70.47 CNY/t with no pass-through
    assert stress.breakeven_price(0.8514, 400, 0.15) == pytest.approx(70.47, rel=1e-3)
    # recovering 30% of the cost means the plant can absorb a price 1 / 0.7 times higher
    assert stress.breakeven_price(0.8514, 400, 0.15, 0.3) == pytest.approx(70.47 / 0.7, rel=1e-3)
    # break-even scales one-for-one with the margin
    assert stress.breakeven_price(0.8514, 400, 0.30) == pytest.approx(2 * 70.47, rel=1e-3)


def test_breakeven_sensitivity_grid():
    cfg = {**CFG, "sensitivity": {
        "country": "CHN", "fuel": "Coal", "ebitda_margin": [0.10, 0.15, 0.20], "pass_through": [0.0, 0.3],
    }}
    res = stress.stress(emissions.add_emissions(_plants(), cfg), cfg)
    sens = report.breakeven_sensitivity(res, cfg)
    assert len(sens) == 3 * 2
    # base case (15% margin, no pass-through in CFG) matches the main stress run
    base = sens[sens["is_base_case"]]
    assert len(base) == 1
    coal = res[res["primary_fuel"] == "Coal"]
    assert base["breakeven_least_efficient"].iloc[0] == pytest.approx(coal["breakeven_price"].min(), abs=0.01)
    assert base["breakeven_most_efficient"].iloc[0] == pytest.approx(70.47, abs=0.01)
    # two 1,000 MW coal plants, so the capacity-weighted value is their simple average
    assert base["breakeven_capacity_weighted"].iloc[0] == pytest.approx(coal["breakeven_price"].mean(), abs=0.01)
    # a higher margin or more pass-through always raises the break-even price
    grid = sens.pivot(index="ebitda_margin", columns="pass_through", values="breakeven_capacity_weighted")
    assert (grid.diff(axis=0).dropna() > 0).all().all()
    assert (grid.diff(axis=1).dropna(axis=1) > 0).all().all()


def _gen_cfg(**overrides):
    return {**CFG, "generation": {**CFG["generation"], **overrides}}


def _two_province_plants():
    df = _plants()
    df.loc[0, "province"] = "Other"   # old coal moves to a second province
    return df


def test_province_capacity_factor_override():
    base = emissions.add_emissions(_two_province_plants(), CFG)
    cfg = _gen_cfg(capacity_factor_by_province={"Coal": {"Test": 0.40}})
    df = emissions.add_emissions(_two_province_plants(), cfg)
    # New coal in "Test": 1,000 MW x 8,760 h x 0.40
    assert df.loc[1, "generation_mwh"] == pytest.approx(3_504_000)
    assert df.loc[1, "emissions_tco2"] == pytest.approx(3_504_000 * df.loc[1, "ef_tco2_mwh"])
    # Coal in "Other" and gas in "Test" keep their GPPD generation
    assert df.loc[0, "generation_mwh"] == base.loc[0, "generation_mwh"]
    assert df.loc[2, "generation_mwh"] == base.loc[2, "generation_mwh"]


def test_province_override_wins_over_fuel_override():
    cfg = _gen_cfg(capacity_factor_override={"Coal": 0.60},
                   capacity_factor_by_province={"Coal": {"Test": 0.40}})
    df = emissions.add_emissions(_two_province_plants(), cfg)
    assert df.loc[0, "generation_mwh"] == pytest.approx(1000 * 8760 * 0.60)  # fuel-wide value
    assert df.loc[1, "generation_mwh"] == pytest.approx(1000 * 8760 * 0.40)  # province value


def test_capacity_factor_scales_cost_but_not_flags():
    # Carbon cost and revenue both scale with generation, so cost share, flags and
    # break-even depend only on the emission factor, not on the capacity factor.
    base = stress.stress(emissions.add_emissions(_plants(), CFG), CFG)
    cfg = _gen_cfg(capacity_factor_by_province={"Coal": {"Test": 0.40}})
    res = stress.stress(emissions.add_emissions(_plants(), cfg), cfg)
    b, r = base[base["gppd_idnr"] == "b"].iloc[0], res[res["gppd_idnr"] == "b"].iloc[0]
    assert r["carbon_cost"] == pytest.approx(b["carbon_cost"] * 3504 / 5000)
    assert r["cost_share"] == pytest.approx(b["cost_share"])
    assert r["flag"] == b["flag"] and r["breakeven_price"] == pytest.approx(b["breakeven_price"])


@pytest.mark.parametrize("by_province, message", [
    ({"Coal": {"Tset": 0.40}}, "no plants in"),               # misspelt province
    ({"Coal": {"Test": 1.20}}, "at most 1"),                  # more hours than in a year
    ({"Coal": {"Test": 0.0}}, "above 0"),
])
def test_bad_province_override_is_rejected(by_province, message):
    with pytest.raises(ValueError, match=message):
        emissions.add_emissions(_plants(), _gen_cfg(capacity_factor_by_province=by_province))


# Years to break-even: two study years, so the path between them is interpolated.
#   ramp:  price 100 -> 220, paid share 0.2 -> 0.7 (2025 -> 2030)
#   flat:  50 x 0.5 = 25 every year (never reaches any plant's break-even)
#   high:  300 x 0.5 = 150 from the start (every plant already cash-negative)
def _ytb_cfg():
    def path(p0, p1, s0, s1):
        return {"CHN": {"carbon_price": {2025: p0, 2030: p1}, "uncovered_share": {2025: s0, 2030: s1}}}
    return {**CFG, "study_years": [2025, 2030], "headline": {"scenario": "ramp", "year": 2030},
            "scenarios": {"ramp": {"label": "ramp", **path(100, 220, 0.2, 0.7)},
                          "flat": {"label": "flat", **path(50, 50, 0.5, 0.5)},
                          "high": {"label": "high", **path(300, 300, 0.5, 0.5)}}}


def test_annual_effective_price_interpolates_price_and_share_separately():
    eff = stress.annual_effective_price(_ytb_cfg()["scenarios"]["ramp"]["CHN"], [2025, 2030])
    assert list(eff.index) == list(range(2025, 2031))
    # 2027: price 100 + 2 x 24 = 148, share 0.2 + 2 x 0.1 = 0.4 -> 59.2 (not the straight-line 68)
    assert eff[2027] == pytest.approx(148 * 0.4)
    assert eff[2025] == pytest.approx(20) and eff[2030] == pytest.approx(154)


def test_breakeven_years_by_plant_and_scenario():
    cfg = _ytb_cfg()
    res = stress.stress(emissions.add_emissions(_plants(), cfg), cfg)
    by = stress.breakeven_years(res, cfg).set_index(["scenario", "gppd_idnr"])["breakeven_year"]
    # Break-even prices: old coal 0.15 x 400 / 1.0320 = 58.1, new coal 70.5, gas 148.5 CNY/t.
    # Ramp path: 2026 37.2, 2027 59.2, 2028 86.0, 2029 117.6, 2030 154.0
    assert by["ramp", "a"] == 2027   # old, least efficient coal goes first
    assert by["ramp", "b"] == 2028
    assert by["ramp", "c"] == 2030   # gas only just crosses in the last study year
    assert by["flat"].isna().all()   # 25 CNY/t never reaches break-even
    assert (by["high"] == 2025).all()


def test_breakeven_year_matches_flags_at_study_years():
    # On a rising path, a plant is flagged High in a study year exactly when it has
    # reached break-even by then.
    cfg = _ytb_cfg()
    res = stress.stress(emissions.add_emissions(_plants(), cfg), cfg)
    by = stress.breakeven_years(res, cfg)
    m = res.merge(by, on=["gppd_idnr", "scenario"])
    assert ((m["flag"] == "High") == (m["breakeven_year"] <= m["year"])).all()


def test_years_to_breakeven_table():
    cfg = _ytb_cfg()
    res = stress.stress(emissions.add_emissions(_plants(), cfg), cfg)
    table = report.years_to_breakeven(res, stress.breakeven_years(res, cfg), cfg)
    assert list(table["gppd_idnr"]) == ["a", "b", "c"]   # wind excluded; soonest first under "ramp"
    assert list(table.columns[-3:]) == [
        "years_to_breakeven_ramp", "years_to_breakeven_flat", "years_to_breakeven_high",
    ]
    row = table.set_index("gppd_idnr").loc["b"]
    assert row["years_to_breakeven_ramp"] == 3        # 2028 - 2025
    assert math.isnan(row["years_to_breakeven_flat"])  # blank in the CSV
    assert row["years_to_breakeven_high"] == 0
