"""Comptages routiers du Département de l'Hérault (routes départementales)."""
from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

from .. import CRS_METRIQUE, CRS_WEB
from ..http import telecharger

ID = "Identifiant du compteur"


def _lire_csv(chemin) -> pd.DataFrame:
    # Séparateur non documenté : on le détecte.
    return pd.read_csv(chemin, sep=None, engine="python", dtype=str, encoding="utf-8-sig")


def sections(cfg: dict) -> gpd.GeoDataFrame:
    comptages = _lire_csv(telecharger(cfg["sources"]["trafic_comptages"], ".csv"))
    comptages["annee"] = pd.to_numeric(comptages["Année"], errors="coerce")
    comptages["tmja"] = pd.to_numeric(comptages["mja_tv_tcj"], errors="coerce")
    comptages["pl_pct"] = pd.to_numeric(comptages["mja_%pl_tcj"], errors="coerce")
    comptages = comptages.dropna(subset=["tmja", "annee"])
    derniers = comptages.sort_values("annee").groupby(ID).tail(1)

    sect = _lire_csv(telecharger(cfg["sources"]["trafic_sections"], ".csv"))
    sect = sect.dropna(subset=["geo_shape"])
    sect["geometry"] = sect["geo_shape"].map(lambda s: shape(json.loads(s)))
    lignes = gpd.GeoDataFrame(sect[[ID, "geometry"]], geometry="geometry", crs=CRS_WEB)
    lignes = lignes.merge(derniers[[ID, "tmja", "pl_pct", "annee"]], on=ID, how="inner")

    # Compteurs sans section : on garde leur position ponctuelle.
    sans = derniers[~derniers[ID].isin(lignes[ID])].copy()
    sans["lat"] = pd.to_numeric(sans["Latitude"], errors="coerce")
    sans["lon"] = pd.to_numeric(sans["Longitude"], errors="coerce")
    sans = sans.dropna(subset=["lat", "lon"])
    points = gpd.GeoDataFrame(sans[[ID, "tmja", "pl_pct", "annee"]],
                              geometry=gpd.points_from_xy(sans["lon"], sans["lat"]), crs=CRS_WEB)
    tout = pd.concat([lignes, points], ignore_index=True)
    g = gpd.GeoDataFrame(tout, geometry="geometry", crs=CRS_WEB).to_crs(CRS_METRIQUE)
    g["source"] = "comptage CD34"
    return g.rename(columns={ID: "compteur"})[["compteur", "tmja", "pl_pct", "annee", "source", "geometry"]]
