"""Agent Trafic : trafic moyen journalier de la route la plus proche.

Comptages du Département quand ils existent ; sinon estimation selon la classe
de la route (routes nationales), décotée et signalée.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from .outils import NEUTRE, log_croissant


def _plus_proche(cand, couche, rayon, cols):
    j = gpd.sjoin_nearest(cand[["geometry"]], couche[cols + ["geometry"]], how="left",
                          max_distance=rayon, distance_col="_d")
    return j[~j.index.duplicated(keep="first")]


def noter(candidats, d, cfg) -> pd.DataFrame:
    out = pd.DataFrame(index=candidats.index)
    out["trafic_tmja"] = np.nan
    out["trafic_source"] = None
    if candidats.empty or (d.trafic.empty and d.routes.empty):
        out["note_trafic"] = NEUTRE
        out["trafic_dispo"] = False
        return out
    rayon = cfg["rayon_m"]
    mesure = pd.Series(np.nan, index=candidats.index)
    if not d.trafic.empty:
        j = _plus_proche(candidats, d.trafic, rayon, ["tmja"])
        mesure = (j["tmja"] * np.exp(-j["_d"] / rayon)).reindex(candidats.index)
    estime = pd.Series(np.nan, index=candidats.index)
    if not d.routes.empty:
        classes = cfg["estimation_par_classe"]
        r = d.routes[d.routes["highway"].isin(classes)].copy()
        if not r.empty:
            r["tmja_est"] = r["highway"].map(classes) * cfg["decote_estimation"]
            j = _plus_proche(candidats, r, rayon, ["tmja_est"])
            estime = (j["tmja_est"] * np.exp(-j["_d"] / rayon)).reindex(candidats.index)
    retenu = mesure.fillna(0).combine(estime.fillna(0), max)
    out["trafic_tmja"] = retenu.replace(0, np.nan).round(0)
    out["trafic_source"] = np.where(mesure.fillna(0) >= estime.fillna(0), "comptage", "estimation")
    out.loc[out["trafic_tmja"].isna(), "trafic_source"] = "aucune route principale"
    out["note_trafic"] = log_croissant(retenu.fillna(0), cfg["tmja_min"], cfg["tmja_ref"]).round(1)
    out["trafic_dispo"] = not d.trafic.empty
    return out
