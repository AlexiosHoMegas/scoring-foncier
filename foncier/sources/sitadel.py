"""Permis de construire de locaux non résidentiels (Sitadel, SDES).

Le fichier « locaux » est repéré automatiquement parmi les ressources du jeu de données
d'après ses colonnes, car les identifiants de ressource peuvent changer.
"""
from __future__ import annotations

import logging
import re
from datetime import date

import geopandas as gpd
import pandas as pd

from .. import CRS_METRIQUE
from ..http import entete, get_json, telecharger

log = logging.getLogger(__name__)
# Surface de plancher créée, toutes destinations non résidentielles confondues.
SURFACE_TOTALE = "SURF_LOC_CREEE"
# Repli si la colonne totale disparaît : somme des destinations non résidentielles.
SURFACES_DETAIL = ["SURF_COM_CREEE", "SURF_BUR_CREEE", "SURF_IND_CREEE", "SURF_ENT_CREEE",
                   "SURF_HEB_CREEE", "SURF_PUB_CREEE", "SURF_AGR_CREEE"]
REQUISES = {"DEP_CODE", "COMM", "DATE_REELLE_AUTORISATION", "SEC_CADASTRE1", "NUM_CADASTRE1"}


def _colonnes(url: str) -> tuple[list[str], str]:
    premiere = entete(url, 32768).split(b"\n", 1)[0].decode("utf-8-sig", errors="replace")
    sep = ";" if premiere.count(";") > premiere.count(",") else ","
    return [c.strip().strip('"') for c in premiere.split(sep)], sep


def _candidates(cfg: dict) -> list[str]:
    """URL configurée d'abord, puis la ressource « locaux non résidentiels » du jeu data.gouv."""
    urls = [u for u in [cfg["sources"].get("sitadel_locaux_csv")] if u]
    try:
        meta = get_json(f"{cfg['sources']['datagouv_api']}/datasets/{cfg['sources']['sitadel_dataset']}/",
                        cache=False)
        for r in meta.get("resources", []):
            titre = (r.get("title") or "").lower()
            if str(r.get("format", "")).lower() == "csv" and "locaux" in titre and r["url"] not in urls:
                urls.append(r["url"])
    except Exception as e:  # noqa: BLE001
        log.warning("API data.gouv indisponible pour Sitadel (%s)", e)
    return urls


def _trouver_ressource(cfg: dict):
    for url in _candidates(cfg):
        cols, sep = _colonnes(url)
        if not REQUISES.issubset(cols):
            log.warning("Sitadel : colonnes inattendues pour %s : %s", url, cols[:40])
            continue
        surfaces = [SURFACE_TOTALE] if SURFACE_TOTALE in cols else [c for c in SURFACES_DETAIL if c in cols]
        if surfaces:
            log.info("Sitadel : %s, surfaces %s", url, surfaces)
            return url, sep, surfaces
    raise ValueError("Fichier Sitadel des locaux introuvable ou de format inattendu")


def _id_parcelle(df: pd.DataFrame) -> pd.Series:
    sec = df["SEC_CADASTRE1"].fillna("").astype(str).str.strip().str.upper().str.zfill(2)
    num = df["NUM_CADASTRE1"].fillna("").astype(str).str.strip().str.replace(r"\D", "", regex=True).str.zfill(4)
    return df["COMM"].astype(str).str.zfill(5) + "000" + sec + num


def permis_locaux(cfg: dict, deps: list[str], parcelles: gpd.GeoDataFrame,
                  communes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    url, sep, surfaces = _trouver_ressource(cfg)
    debut = f"{date.today().year - cfg['agents']['developpement']['annees']}-01-01"
    utiles = set(surfaces) | {"DEP_CODE", "COMM", "DATE_REELLE_AUTORISATION", "SEC_CADASTRE1", "NUM_CADASTRE1"}
    morceaux = []
    for bloc in pd.read_csv(telecharger(url, ".csv"), sep=sep, dtype=str, usecols=lambda c: c in utiles,
                            chunksize=200_000, encoding="utf-8-sig"):
        dates = bloc["DATE_REELLE_AUTORISATION"].fillna("")
        bloc = bloc[bloc["DEP_CODE"].isin(deps) & dates.str.match(r"^\d{4}-\d{2}") & (dates >= debut)]
        if not bloc.empty:
            morceaux.append(bloc)
    if not morceaux:
        raise ValueError("Aucun permis de locaux sur la période")
    df = pd.concat(morceaux, ignore_index=True)
    df["surface_m2"] = df[surfaces].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    df = df[df["surface_m2"] > 0]
    df["id"] = _id_parcelle(df)

    centroides = parcelles.set_index("id").geometry.representative_point()
    df["geometry"] = df["id"].map(centroides)
    # Parcelle non retrouvée : centre de la commune si elle fait partie du territoire.
    centres = communes.set_index("insee").geometry.representative_point()
    manquants = df["geometry"].isna()
    df.loc[manquants, "geometry"] = df.loc[manquants, "COMM"].map(centres)
    df = df.dropna(subset=["geometry"])
    g = gpd.GeoDataFrame(df, geometry="geometry", crs=CRS_METRIQUE)
    return g.rename(columns={"DATE_REELLE_AUTORISATION": "date"})[["date", "surface_m2", "geometry"]]
