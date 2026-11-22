"""Liste des communes du territoire et leurs contours."""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

from .. import CRS_METRIQUE
from ..http import get_json
from . import cadastre


def codes_communes(cfg: dict) -> pd.DataFrame:
    base = cfg["sources"]["geo_api"]
    lignes = []
    for epci in cfg["territoire"].get("epcis", []):
        for c in get_json(f"{base}/epcis/{epci}/communes"):
            lignes.append({"insee": c["code"], "nom": c["nom"]})
    for code in cfg["territoire"].get("communes_supplementaires", []):
        c = get_json(f"{base}/communes/{code}", {"fields": "code,nom"})
        lignes.append({"insee": c["code"], "nom": c["nom"]})
    if not lignes:
        raise ValueError("Aucune commune dans le territoire configuré")
    return pd.DataFrame(lignes).drop_duplicates("insee").reset_index(drop=True)


def communes(cfg: dict) -> gpd.GeoDataFrame:
    liste = codes_communes(cfg)
    contours = []
    for insee in liste["insee"]:
        g = cadastre.charger_commune(cfg, insee, "communes")
        contours.append({"insee": insee, "geometry": g.geometry.union_all()})
    geo = gpd.GeoDataFrame(contours, geometry="geometry", crs=CRS_METRIQUE)
    return geo.merge(liste, on="insee")[["insee", "nom", "geometry"]]
