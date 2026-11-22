"""Cadastre Etalab (GeoJSON par commune)."""
from __future__ import annotations

import gzip
import json

import geopandas as gpd
import pandas as pd

from .. import CRS_METRIQUE, CRS_WEB
from ..http import telecharger


def charger_commune(cfg: dict, insee: str, couche: str) -> gpd.GeoDataFrame:
    url = cfg["sources"]["cadastre"].format(dep=insee[:2], insee=insee, couche=couche)
    chemin = telecharger(url, ".json.gz")
    with gzip.open(chemin, "rt", encoding="utf-8") as f:
        fc = json.load(f)
    g = gpd.GeoDataFrame.from_features(fc["features"], crs=CRS_WEB)
    return g.to_crs(CRS_METRIQUE)


def couche(cfg: dict, communes: gpd.GeoDataFrame, nom: str) -> gpd.GeoDataFrame:
    morceaux = []
    for insee in communes["insee"]:
        g = charger_commune(cfg, insee, nom)
        g["insee"] = insee
        morceaux.append(g)
    g = gpd.GeoDataFrame(pd.concat(morceaux, ignore_index=True), geometry="geometry", crs=CRS_METRIQUE)
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    if nom == "parcelles":
        if "contenance" not in g:
            g["contenance"] = None
        g["contenance"] = pd.to_numeric(g["contenance"], errors="coerce")
        g["contenance"] = g["contenance"].fillna(g.geometry.area)
        g = g[["id", "insee", "contenance", "geometry"]]
    else:
        g = g[["insee", "geometry"]]
    return g.reset_index(drop=True)
