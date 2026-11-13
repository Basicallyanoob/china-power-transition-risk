"""Carbon-cost stress test: scenario x year, plant by plant."""
from __future__ import annotations

import numpy as np
import pandas as pd


def breakeven_price(ef_tco2_mwh, tariff_per_mwh, ebitda_margin, pass_through=0.0):
    """Effective carbon price (per tCO2) at which the absorbed carbon cost uses up the whole margin.

    Solves  ef x price x (1 - pass_through) / tariff = ebitda_margin  for price.
    Works on numbers or pandas Series. pass_through must be below 1 (at 100% the plant
    recovers all of its carbon cost and never breaks even).
    """
    return ebitda_margin * tariff_per_mwh / (ef_tco2_mwh * (1 - pass_through))


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
                out["breakeven_price"] = breakeven_price(
                    out["ef_tco2_mwh"], ccfg["tariff_per_mwh"], ccfg["ebitda_margin"], pt
                )
                rows.append(out)
    res = pd.concat(rows, ignore_index=True)
    res["flag"] = pd.cut(
        res["margin_used"], bins=[-1, watch, 1.0, float("inf")],
        labels=["Low", "Watch", "High"], right=False,
    ).astype(str)
    return res


def annual_effective_price(path: dict, years: list[int]) -> pd.Series:
    """Effective carbon price (price x uncovered share) for every year from the first to the last study year.

    The config gives the price and the uncovered share only at study years.
    ASSUMPTION: each moves in a straight line between study years. They are
    interpolated separately and then multiplied, so the effective price is not
    itself a straight line. Returns a Series indexed by calendar year.
    """
    span = range(min(years), max(years) + 1)
    price = pd.Series({y: path["carbon_price"][y] for y in years}, dtype=float).reindex(span).interpolate()
    paid = pd.Series({y: path["uncovered_share"][y] for y in years}, dtype=float).reindex(span).interpolate()
    return price * paid


def breakeven_years(res: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """One row per fossil plant x scenario: the first year its absorbed carbon cost uses up its margin.

    breakeven_year     = first calendar year in which the (interpolated) effective carbon
                         price reaches the plant's break-even price
    years_to_breakeven = breakeven_year - first study year (0 = already cash-negative then)
    Both are NaN if the price never reaches break-even within the study years.
    """
    years = cfg["study_years"]
    one = res.drop_duplicates(["gppd_idnr", "scenario"])
    rows = []
    for (scen, iso3), g in one.groupby(["scenario", "country"], sort=False):
        eff = annual_effective_price(cfg["scenarios"][scen][iso3], years)
        # Plants down the rows, years across the columns: True where price >= break-even.
        hit = eff.to_numpy()[None, :] >= g["breakeven_price"].to_numpy()[:, None]
        first = eff.index.to_numpy()[hit.argmax(axis=1)]
        out = g[["gppd_idnr", "scenario"]].copy()
        out["breakeven_year"] = np.where(hit.any(axis=1), first, np.nan)
        out["years_to_breakeven"] = out["breakeven_year"] - min(years)
        rows.append(out)
    return pd.concat(rows, ignore_index=True)
