"""Consommation d'espaces naturels, agricoles et forestiers par commune (Cerema, en m²).

Colonnes vérifiées : idcom, naf11art21 (2011-2021), naf21art25 (2021-2025).
"""
from __future__ import annotations

import pandas as pd

from ..http import telecharger


def lire(chemin, communes: list[str]) -> pd.DataFrame:
    df = pd.read_csv(chemin, sep=None, engine="python", dtype={"idcom": str},
                     usecols=["idcom", "naf11art21", "naf21art25"])
    df = df[df["idcom"].isin(communes)]
    return df.rename(columns={"idcom": "insee", "naf11art21": "m2_2011_2021",
                              "naf21art25": "m2_2021_2025"}).reset_index(drop=True)


def charger(cfg: dict, communes: list[str]) -> pd.DataFrame:
    df = lire(telecharger(cfg["sources"]["consoenaf"], ".csv"), communes)
    if df.empty:
        raise ValueError("Communes absentes du fichier de consommation d'espaces")
    return df


def lire_grille(chemin, emprise) -> "gpd.GeoDataFrame":
    """Consommation d'espaces par carreau de 1 km : total récent (2019-2025) et ancien (2013-2019).

    Les colonnes annuelles suivent le motif nafAAartBB (année AA -> BB), comme dans la table
    communale ; on les repère par ce motif plutôt que de figer leurs noms.
    """
    import re

    import geopandas as gpd

    from .. import CRS_METRIQUE

    g = gpd.read_file(chemin)
    if g.crs is None:
        g = g.set_crs(CRS_METRIQUE)
    g = g.to_crs(CRS_METRIQUE)
    g = g[g.intersects(emprise)]
    annuelles = {}
    for c in g.columns:
        m = re.fullmatch(r"naf(\d\d)art(\d\d)", str(c))
        if m and int(m.group(2)) == int(m.group(1)) + 1:
            annuelles[int(m.group(1))] = c
    if len(annuelles) < 6:
        raise ValueError(f"Colonnes annuelles introuvables dans la grille : {list(g.columns)[:30]}")
    derniere = max(annuelles)
    recentes = [annuelles[a] for a in annuelles if a > derniere - 6]
    anciennes = [annuelles[a] for a in annuelles if derniere - 12 < a <= derniere - 6]
    out = gpd.GeoDataFrame({
        "m2_recent": g[recentes].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1),
        "m2_ancien": g[anciennes].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1),
    }, geometry=g.geometry.values, crs=CRS_METRIQUE)
    out.attrs["periode_recente"] = f"20{min(a for a in annuelles if a > derniere - 6):02d}-20{derniere + 1:02d}"
    return out.reset_index(drop=True)


def grille(cfg: dict, communes) -> "gpd.GeoDataFrame":
    emprise = communes.geometry.union_all().buffer(5000)
    return lire_grille(telecharger(cfg["sources"]["consoenaf_grille"], ".gpkg"), emprise)
