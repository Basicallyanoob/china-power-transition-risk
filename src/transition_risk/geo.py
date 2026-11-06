"""Assign each plant to a province (China) or county (Ireland)."""
from __future__ import annotations

import geopandas as gpd
import pandas as pd


def assign_provinces(plants: pd.DataFrame, admin1: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Spatially join plants to admin-1 areas.

    Plants that fall just outside a boundary (coastal plants, coordinate rounding)
    are matched to the nearest area within 25 km. Anything further stays unassigned.
    """
    pts = gpd.GeoDataFrame(
        plants,
        geometry=gpd.points_from_xy(plants["longitude"], plants["latitude"]),
        crs="EPSG:4326",
    )
    areas = admin1[["province", "province_zh", "geometry"]]
    joined = gpd.sjoin(pts, areas, how="left", predicate="within").drop(columns="index_right")
    joined = joined[~joined.index.duplicated(keep="first")]

    missing = joined["province"].isna()
    if missing.any():
        # Nearest-match in a metric projection (World Equidistant Cylindrical).
        miss = joined.loc[missing, pts.columns].to_crs("EPSG:4087")
        near = gpd.sjoin_nearest(
            miss, areas.to_crs("EPSG:4087"), how="left", max_distance=25_000
        )
        near = near[~near.index.duplicated(keep="first")]
        joined.loc[missing, "province"] = near["province"]
        joined.loc[missing, "province_zh"] = near["province_zh"]

    joined["province"] = joined["province"].fillna("Unassigned")
    return joined
