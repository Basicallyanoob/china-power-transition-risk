"""Carbon-cost stress test: scenario x year, plant by plant."""
from __future__ import annotations

import pandas as pd


def stress(plants: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Long table: one row per fossil plant x scenario x year.

    effective_price  = carbon price x uncovered (paid) share
    carbon_cost      = emissions x effective_price                (gross, before recovery)
    net_carbon_cost  = carbon_cost x (1 - pass_through)           (what the plant absorbs)
    revenue          = generation x tariff
    cost_share       = net_carbon_cost / revenue
    margin_used      = cost_share / baseline EBITDA margin
    breakeven_price  = effective carbon price at which margin_used = 1
    flag             = High (margin_used >= 1), Watch (>= watch fraction), Low
    """
    fossil = plants[plants["is_fossil"] & (plants["generation_mwh"] > 0)]
    watch = cfg["flags"]["watch_fraction_of_margin"]
    rows = []
    for scen_key, scen in cfg["scenarios"].items():
        for iso3, ccfg in cfg["countries"].items():
            sub = fossil[fossil["country"] == iso3]
            if sub.empty or iso3 not in scen:
                continue
            path = scen[iso3]
            for year in cfg["study_years"]:
                price = path["carbon_price"][year]
                paid = path["uncovered_share"][year]
                out = sub[[
                    "gppd_idnr", "name", "country", "province", "province_zh", "owner",
                    "primary_fuel", "capacity_mw", "commissioning_year", "latitude",
                    "longitude", "generation_mwh", "ef_tco2_mwh", "emissions_tco2",
                ]].copy()
                out["scenario"] = scen_key
                out["year"] = year
                out["currency"] = ccfg["currency"]
                out["carbon_price"] = price
                out["uncovered_share"] = paid
                pt = ccfg.get("pass_through", 0.0)
                out["effective_price"] = price * paid
                out["carbon_cost"] = out["emissions_tco2"] * price * paid
                out["net_carbon_cost"] = out["carbon_cost"] * (1 - pt)
                out["revenue"] = out["generation_mwh"] * ccfg["tariff_per_mwh"]
                out["cost_share"] = out["net_carbon_cost"] / out["revenue"]
                out["margin_used"] = out["cost_share"] / ccfg["ebitda_margin"]
                out["breakeven_price"] = (
                    ccfg["ebitda_margin"] * ccfg["tariff_per_mwh"] / (out["ef_tco2_mwh"] * (1 - pt))
                )
                rows.append(out)
    res = pd.concat(rows, ignore_index=True)
    res["flag"] = pd.cut(
        res["margin_used"], bins=[-1, watch, 1.0, float("inf")],
        labels=["Low", "Watch", "High"], right=False,
    ).astype(str)
    return res
