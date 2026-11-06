"""Aggregate results and draw the figures used in the README."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Font fallback so Chinese province names render on Linux, Windows and macOS.
plt.rcParams["font.family"] = ["DejaVu Sans", "Noto Sans CJK SC", "Microsoft YaHei", "SimHei", "PingFang SC"]

SCEN_COLOURS = {"current_policies": "#7f8c8d", "delayed_transition": "#e67e22", "net_zero": "#2471a3"}


def _style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    ax.set_axisbelow(True)


def fleet_summary(plants: pd.DataFrame) -> pd.DataFrame:
    """Capacity and emissions by country and fuel."""
    g = plants.groupby(["country", "primary_fuel"], as_index=False).agg(
        plants=("gppd_idnr", "count"),
        capacity_gw=("capacity_mw", lambda s: s.sum() / 1000),
        emissions_mtco2=("emissions_tco2", lambda s: s.sum() / 1e6),
    )
    return g.sort_values(["country", "capacity_gw"], ascending=[True, False]).round(2)


def scenario_path(res: pd.DataFrame) -> pd.DataFrame:
    """Total carbon cost and flagged capacity by country, scenario and year."""
    g = res.groupby(["country", "currency", "scenario", "year"], as_index=False).agg(
        carbon_cost_bn=("carbon_cost", lambda s: s.sum() / 1e9),
        high_capacity_gw=("capacity_mw", lambda s: s[res.loc[s.index, "flag"] == "High"].sum() / 1000),
        fossil_capacity_gw=("capacity_mw", lambda s: s.sum() / 1000),
    )
    g["high_share_of_fossil_capacity"] = g["high_capacity_gw"] / g["fossil_capacity_gw"]
    return g.round(3)


def province_exposure(res: pd.DataFrame, scenario: str, year: int) -> pd.DataFrame:
    sub = res[(res["country"] == "CHN") & (res["scenario"] == scenario) & (res["year"] == year)]
    g = sub.groupby(["province", "province_zh"], as_index=False).agg(
        fossil_plants=("gppd_idnr", "count"),
        fossil_capacity_gw=("capacity_mw", lambda s: s.sum() / 1000),
        emissions_mtco2=("emissions_tco2", lambda s: s.sum() / 1e6),
        carbon_cost_cny_bn=("carbon_cost", lambda s: s.sum() / 1e9),
        net_carbon_cost_cny_bn=("net_carbon_cost", lambda s: s.sum() / 1e9),
        high_flag_capacity_gw=("capacity_mw", lambda s: s[sub.loc[s.index, "flag"] == "High"].sum() / 1000),
    )
    g["share_high_flag"] = g["high_flag_capacity_gw"] / g["fossil_capacity_gw"]
    return g.sort_values("carbon_cost_cny_bn", ascending=False).round(3)


def owner_exposure(res: pd.DataFrame, scenario: str, year: int, top: int = 20) -> pd.DataFrame:
    sub = res[(res["country"] == "CHN") & (res["scenario"] == scenario) & (res["year"] == year)].copy()
    sub["owner"] = sub["owner"].fillna("Owner not reported")
    g = sub.groupby("owner", as_index=False).agg(
        plants=("gppd_idnr", "count"),
        capacity_gw=("capacity_mw", lambda s: s.sum() / 1000),
        carbon_cost_cny_bn=("carbon_cost", lambda s: s.sum() / 1e9),
    )
    return g.sort_values("carbon_cost_cny_bn", ascending=False).head(top).round(3)


def watchlist(res: pd.DataFrame, scenario: str, year: int, top: int = 50) -> pd.DataFrame:
    sub = res[(res["country"] == "CHN") & (res["scenario"] == scenario) & (res["year"] == year)]
    cols = [
        "gppd_idnr", "name", "province", "province_zh", "owner", "primary_fuel", "capacity_mw",
        "commissioning_year", "ef_tco2_mwh", "emissions_tco2", "carbon_cost", "net_carbon_cost",
        "cost_share", "margin_used", "breakeven_price", "flag",
    ]
    out = sub.sort_values("carbon_cost", ascending=False)[cols].head(top).copy()
    out["emissions_mtco2"] = out.pop("emissions_tco2") / 1e6
    out["carbon_cost_cny_m"] = out.pop("carbon_cost") / 1e6
    out["net_carbon_cost_cny_m"] = out.pop("net_carbon_cost") / 1e6
    out = out.rename(columns={"breakeven_price": "breakeven_effective_price_cny_t"})
    return out.round(3)


def breakeven_by_vintage(res: pd.DataFrame) -> pd.DataFrame:
    """Break-even effective carbon price by country, fuel and efficiency band."""
    one = res.drop_duplicates("gppd_idnr")
    g = one.groupby(["country", "currency", "primary_fuel", "ef_tco2_mwh"], as_index=False).agg(
        plants=("gppd_idnr", "count"),
        capacity_gw=("capacity_mw", lambda s: s.sum() / 1000),
        breakeven_effective_price=("breakeven_price", "first"),
    )
    return g.sort_values(["country", "breakeven_effective_price"]).round(2)


# ---------------------------------------------------------------- figures

def fig_breakeven(res: pd.DataFrame, be: pd.DataFrame, cfg: dict, out: Path) -> None:
    """China: effective carbon price by scenario-year vs the fleet's break-even band."""
    cn = res[res["country"] == "CHN"].drop_duplicates(["scenario", "year"])
    cb = be[(be["country"] == "CHN") & (be["primary_fuel"] == "Coal")]
    lo, hi = cb["breakeven_effective_price"].min(), cb["breakeven_effective_price"].max()
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    ax.axhspan(lo, hi, color="#c0392b", alpha=0.12, lw=0)
    ax.text(cfg["study_years"][-1], hi + 14, f"Coal break-even band {lo:.0f}–{hi:.0f} CNY/t\n"
            "(oldest to newest plants)", fontsize=9, color="#922b21", ha="right", va="bottom")
    for scen, g in cn.groupby("scenario"):
        ax.plot(g["year"], g["effective_price"], marker="o", color=SCEN_COLOURS.get(scen),
                label=cfg["scenarios"][scen]["label"])
    ax.set_ylabel("Effective carbon price, CNY/tCO2\n(price x share of emissions paid for)")
    ax.set_xticks(cfg["study_years"])
    ax.set_title("Chinese coal plants turn cash-negative once the effective carbon price\n"
                 "crosses the break-even band", loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=9, loc="upper left", bbox_to_anchor=(0, 0.9))
    _style(ax)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def fig_scenarios(path: pd.DataFrame, cfg: dict, out: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, iso3 in zip(axes, ["CHN", "IRL"]):
        sub = path[path["country"] == iso3]
        for scen, g in sub.groupby("scenario"):
            ax.plot(g["year"], g["high_share_of_fossil_capacity"] * 100, marker="o",
                    color=SCEN_COLOURS.get(scen), label=cfg["scenarios"][scen]["label"])
        ax.set_title(f"{cfg['countries'][iso3]['name']}: fossil capacity flagged High", loc="left", fontsize=11)
        ax.set_ylabel("% of fossil capacity")
        ax.set_ylim(-3, 103)
        ax.set_xticks(cfg["study_years"])
        _style(ax)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=9, ncol=3, loc="lower center")
    fig.suptitle("Share of fossil capacity whose absorbed carbon cost exceeds its EBITDA margin", x=0.01, ha="left", fontsize=12, weight="bold")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out, dpi=160)
    plt.close(fig)


def fig_provinces(prov: pd.DataFrame, scenario_label: str, year: int, out: Path, top: int = 15) -> None:
    d = prov.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.barh(d["province"] + "  " + d["province_zh"], d["carbon_cost_cny_bn"], color="#2c3e50")
    for y, v in enumerate(d["carbon_cost_cny_bn"]):
        ax.text(v, y, f" {v:,.0f}", va="center", fontsize=8.5)
    ax.set_xlabel("Annual carbon allowance cost, CNY bn (before pass-through)")
    ax.set_title(f"Top {top} provinces by annual carbon allowance cost\n{scenario_label}, {year}", loc="left", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
