"""Run the full pipeline:  python -m transition_risk [--config path] [--download]"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml

from . import data, emissions, geo, report, stress

ROOT = Path(__file__).resolve().parents[2]


def run(plants: pd.DataFrame, admin1: gpd.GeoDataFrame, cfg: dict, out: Path) -> dict:
    """Run every model step on already-loaded inputs and write all outputs to `out`.

    Kept separate from `main()` so tests can run the same pipeline on a small
    sample without downloading the full datasets.
    """
    plants = geo.assign_provinces(plants, admin1)
    plants = emissions.add_emissions(plants, cfg)
    res = stress.stress(plants, cfg)

    h_scen, h_year = cfg["headline"]["scenario"], cfg["headline"]["year"]
    h_label = cfg["scenarios"][h_scen]["label"]
    figs = out / "figures"
    figs.mkdir(parents=True, exist_ok=True)

    fleet = report.fleet_summary(plants)
    path = report.scenario_path(res)
    prov = report.province_exposure(res, h_scen, h_year)
    owners = report.owner_exposure(res, h_scen, h_year)
    watch = report.watchlist(res, h_scen, h_year)
    be = report.breakeven_by_vintage(res)
    sens = report.breakeven_sensitivity(res, cfg)

    fleet.to_csv(out / "fleet_summary.csv", index=False)
    path.to_csv(out / "scenario_paths.csv", index=False)
    prov.to_csv(out / "province_exposure.csv", index=False, encoding="utf-8-sig")
    owners.to_csv(out / "owner_exposure.csv", index=False, encoding="utf-8-sig")
    watch.to_csv(out / "plant_watchlist_top50.csv", index=False, encoding="utf-8-sig")
    be.to_csv(out / "breakeven_by_vintage.csv", index=False)
    sens.to_csv(out / "breakeven_sensitivity.csv", index=False)

    report.fig_scenarios(path, cfg, figs / "flagged_capacity_by_scenario.png")
    report.fig_breakeven(res, be, cfg, figs / "breakeven_vs_scenarios.png")
    report.fig_provinces(prov, h_label, h_year, figs / "province_carbon_cost.png")

    summary = {
        "plants_loaded": int(len(plants)),
        "unassigned_province": int((plants["province"] == "Unassigned").sum()),
        "fossil_plants_stressed": int(res["gppd_idnr"].nunique()),
        "headline": {"scenario": h_scen, "year": h_year},
    }
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=ROOT / "config" / "assumptions.yaml", type=Path)
    ap.add_argument("--download", action="store_true", help="fetch the input datasets first")
    ap.add_argument("--out", default=ROOT / "outputs", type=Path)
    args = ap.parse_args()

    cfg = yaml.safe_load(args.config.read_text())
    if args.download or not data.GPPD_PATH.exists() or not data.ADMIN1_PATH.exists():
        data.download()

    plants = data.load_plants(list(cfg["countries"]))
    admin1 = data.load_admin1(list(cfg["countries"]))
    summary = run(plants, admin1, cfg, args.out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
