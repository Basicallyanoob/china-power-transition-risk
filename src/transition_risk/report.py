"""Aggregate results and draw the figures used in the README."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .stress import breakeven_price

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


def breakeven_sensitivity(res: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Break-even effective carbon price over a grid of EBITDA margin x pass-through.

    For one country and fuel (config `sensitivity`), recomputes every plant's break-even
    price for each margin and pass-through in the grid, keeping the tariff and emission
    factors fixed. One row per grid point: the range across plants (least to most
    efficient) and the capacity-weighted average.
    """
    sens = cfg["sensitivity"]
    iso3, fuel = sens["country"], sens["fuel"]
    ccfg = cfg["countries"][iso3]
    one = res[(res["country"] == iso3) & (res["primary_fuel"] == fuel)].drop_duplicates("gppd_idnr")
    rows = []
    for margin in sens["ebitda_margin"]:
        for pt in sens["pass_through"]:
            be = breakeven_price(one["ef_tco2_mwh"], ccfg["tariff_per_mwh"], margin, pt)
            rows.append({
                "country": iso3,
                "currency": ccfg["currency"],
                "primary_fuel": fuel,
                "ebitda_margin": margin,
                "pass_through": pt,
                "is_base_case": bool(
                    abs(margin - ccfg["ebitda_margin"]) < 1e-9
                    and abs(pt - ccfg.get("pass_through", 0.0)) < 1e-9
                ),
                "breakeven_least_efficient": be.min(),
                "breakeven_capacity_weighted": (be * one["capacity_mw"]).sum() / one["capacity_mw"].sum(),
                "breakeven_most_efficient": be.max(),
            })
    return pd.DataFrame(rows).round(2)


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


# One blue, light to dark, for the ordered pass-through rates (low to high).
# Checked as an ordinal ramp: lightness rises step by step and the light end stays visible on white.
PASS_THROUGH_BLUES = ["#6da7ec", "#2a78d6", "#104281"]


def fig_sensitivity(sens: pd.DataFrame, cfg: dict, out: Path) -> None:
    """Break-even effective carbon price vs EBITDA margin, one line per pass-through rate.

    Dots are the capacity-weighted average across plants; thin bars span the least to
    the most efficient plant. The base-case grid point is ringed and labelled.
    """
    pts = sorted(sens["pass_through"].unique())
    if len(pts) > len(PASS_THROUGH_BLUES):
        raise ValueError(f"fig_sensitivity draws up to {len(PASS_THROUGH_BLUES)} pass-through rates; got {len(pts)}")
    colours = dict(zip(pts, PASS_THROUGH_BLUES))
    margins = sorted(sens["ebitda_margin"].unique())
    step = (margins[1] - margins[0]) * 100 if len(margins) > 1 else 5
    offsets = {pt: (i - (len(pts) - 1) / 2) * step * 0.08 for i, pt in enumerate(pts)}
    cur = sens["currency"].iloc[0]

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    for pt in pts:
        g = sens[sens["pass_through"] == pt].sort_values("ebitda_margin")
        x = g["ebitda_margin"] * 100 + offsets[pt]
        ax.vlines(x, g["breakeven_least_efficient"], g["breakeven_most_efficient"],
                  color=colours[pt], linewidth=2, alpha=0.45)
        ax.plot(x, g["breakeven_capacity_weighted"], color=colours[pt], linewidth=2,
                marker="o", markersize=7, markeredgecolor="white", markeredgewidth=1.5,
                label=f"{pt:.0%} pass-through")
        last = g.iloc[-1]
        ax.text(x.iloc[-1] + step * 0.12, last["breakeven_capacity_weighted"],
                f"{pt:.0%} pass-through", fontsize=9, color="#374151", va="center")

    base = sens[sens["is_base_case"]]
    if not base.empty:
        b = base.iloc[0]
        bx = b["ebitda_margin"] * 100 + offsets[b["pass_through"]]
        by = b["breakeven_capacity_weighted"]
        ax.plot(bx, by, marker="o", markersize=15, markerfacecolor="none",
                markeredgecolor="#111827", markeredgewidth=1.5, linestyle="none")
        ax.annotate(f"Base case: {b['ebitda_margin']:.0%} margin, {b['pass_through']:.0%} pass-through\n"
                    f"{by:.0f} {cur}/t (plants {b['breakeven_least_efficient']:.0f}–"
                    f"{b['breakeven_most_efficient']:.0f})",
                    xy=(bx, by), xytext=(bx - step * 0.9, by + 30), fontsize=9, color="#111827",
                    ha="left", arrowprops=dict(arrowstyle="-", color="#6b7280", lw=0.8))

    ax.set_xticks([m * 100 for m in margins], [f"{m:.0%}" for m in margins])
    ax.set_xlim(margins[0] * 100 - step * 0.5, margins[-1] * 100 + step * 0.9)
    ax.set_ylim(0, sens["breakeven_most_efficient"].max() * 1.15)
    ax.set_xlabel("Baseline EBITDA margin before carbon cost (ASSUMPTION)")
    ax.set_ylabel(f"Break-even effective carbon price, {cur}/tCO2")
    ax.set_title(f"{cfg['countries'][sens['country'].iloc[0]]['name']} {sens['primary_fuel'].iloc[0].lower()}: "
                 "break-even effective carbon price\nunder different margin and pass-through assumptions",
                 loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.text(0.01, 0.01, "Dots: capacity-weighted average across plants. Bars: least to most efficient plant. "
             "Tariff and emission factors as in the main run.", fontsize=8, color="#6b7280")
    _style(ax)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
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
