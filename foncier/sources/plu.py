"""Géoportail de l'urbanisme via l'API Carto de l'IGN.

L'API renvoie au plus 5 000 objets par requête : on interroge commune par commune,
en découpant l'emprise en quatre tant que la limite est atteinte.
"""
from __future__ import annotations

import json
import logging

import geopandas as gpd
import pandas as pd
from shapely.geometry import box, mapping

from .. import CRS_METRIQUE, CRS_WEB
from ..donnees import gdf_vide
from ..http import get_json

log = logging.getLogger(__name__)
LIMITE_API = 5000


def _interroger(base: str, ressource: str, emprise, extra: dict, profondeur: int = 0) -> list[dict]:
    params = {"geom": json.dumps(mapping(emprise)), **extra}
    fc = get_json(f"{base}/{ressource}", params)
    feats = fc.get("features", [])
    if len(feats) >= LIMITE_API and profondeur < 6:
        minx, miny, maxx, maxy = emprise.bounds
        mx, my = (minx + maxx) / 2, (miny + maxy) / 2
        feats = []
        for b in (box(minx, miny, mx, my), box(mx, miny, maxx, my),
                  box(minx, my, mx, maxy), box(mx, my, maxx, maxy)):
            feats += _interroger(base, ressource, b, extra, profondeur + 1)
    return feats


def _couche(cfg: dict, communes: gpd.GeoDataFrame, ressource: str, extra: dict | None = None):
    base = cfg["sources"]["apicarto_gpu"]
    feats = []
    for geom in communes.to_crs(CRS_WEB).geometry:
        feats += _interroger(base, ressource, box(*geom.bounds), extra or {})
    if not feats:
        return gdf_vide()
    g = gpd.GeoDataFrame.from_features(feats, crs=CRS_WEB).to_crs(CRS_METRIQUE)
    g.columns = [c.lower() if c != "geometry" else c for c in g.columns]
    cles = [c for c in ("gid", "id", "idurba", "libelle", "typezone", "typepsc") if c in g]
    g["_wkb"] = g.geometry.to_wkb()
    g = g.drop_duplicates(subset=cles + ["_wkb"]).drop(columns="_wkb")
    return g.reset_index(drop=True)


def zones(cfg: dict, communes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    g = _couche(cfg, communes, "zone-urba")
    if g.empty:
        raise ValueError("Aucun zonage d'urbanisme renvoyé par le GPU")
    # Le standard CNIG 2024 a renommé DESTDOMI en FORMDOMI : on accepte les deux.
    formdomi = g["formdomi"] if "formdomi" in g else pd.Series(None, index=g.index)
    if "destdomi" in g:
        formdomi = formdomi.fillna(g["destdomi"])
    g["formdomi"] = formdomi.astype("string")
    for c in ("typezone", "libelle", "libelong", "urlfic", "partition"):
        if c not in g:
            g[c] = None
    return g[["typezone", "libelle", "libelong", "formdomi", "urlfic", "partition", "geometry"]]


def prescriptions(cfg: dict, communes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    g = _couche(cfg, communes, "prescription-surf")
    if g.empty:
        return gdf_vide(["typepsc", "libelle"])
    g["typepsc"] = g["typepsc"].astype(str).str.zfill(2)
    if "libelle" not in g:
        g["libelle"] = None
    return g[["typepsc", "libelle", "geometry"]]


def ppr(cfg: dict, communes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Assiettes des servitudes PM1 (plans de prévention des risques naturels)."""
    g = _couche(cfg, communes, "assiette-sup-s", {"categorie": "PM1"})
    if g.empty:
        return gdf_vide()
    return g[["geometry"]]
