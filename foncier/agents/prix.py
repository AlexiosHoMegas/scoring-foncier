"""Agent Prix : prix des terrains comparables autour de la parcelle, et estimation de sa valeur.

Comparables = ventes DVF de terrains nus situées en zone constructible (U, AU), dans un rayon
de 2 km, élargi à 5 km s'il y a moins de 5 ventes. Estimation = surface × prix médian au m²,
avec une fourchette du premier au troisième quartile. La note est d'autant plus haute que le
foncier du secteur est bon marché.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .outils import NEUTRE, rang


def comparables(ventes: gpd.GeoDataFrame, zones: gpd.GeoDataFrame, typezones: list[str]) -> gpd.GeoDataFrame:
    """Ne garde que les ventes situées dans une zone constructible."""
    if zones.empty or not typezones:
        return ventes
    z = zones[zones["typezone"].isin(typezones)][["geometry"]]
    dedans = gpd.sjoin(ventes, z, how="inner", predicate="within").index.unique()
    return ventes.loc[dedans]


def _quartiles(points, ventes, rayon: float) -> pd.DataFrame:
    arbre = shapely.STRtree(ventes.geometry.values)
    i_cand, i_vente = arbre.query(points.values, predicate="dwithin", distance=rayon)
    prix = ventes["prix_m2"].to_numpy()
    g = pd.DataFrame({"c": i_cand, "p": prix[i_vente]}).groupby("c")["p"]
    return pd.DataFrame({"q1": g.quantile(0.25), "med": g.median(), "q3": g.quantile(0.75), "nb": g.size()})


def _estimer(cands, ventes, cfg) -> pd.DataFrame:
    points = cands.geometry.representative_point().reset_index(drop=True)
    if ventes.empty:
        q = pd.DataFrame({"q1": np.nan, "med": np.nan, "q3": np.nan, "nb": 0.0}, index=range(len(points)))
    else:
        q = _quartiles(points, ventes, cfg["rayon_m"]).reindex(range(len(points)))
        q["nb"] = q["nb"].fillna(0)
        # Pas assez de ventes : on élargit le rayon.
        faibles = q.index[q["nb"] < cfg["ventes_min"]]
        if len(faibles):
            q2 = _quartiles(points.iloc[faibles].reset_index(drop=True), ventes, cfg["rayon_max_m"])
            q2.index = faibles[q2.index]
            q.loc[q2.index] = q2
    q.index = cands.index
    return q


def noter(candidats, d, cfg) -> pd.DataFrame:
    out = pd.DataFrame(index=candidats.index)
    for c in ["prix_m2_median", "prix_estime", "prix_estime_bas", "prix_estime_haut"]:
        out[c] = np.nan
    out["prix_nb_ventes"] = 0
    out["prix_base"] = None
    if d.ventes.empty or candidats.empty:
        out["note_prix"] = NEUTRE
        out["prix_dispo"] = False
        return out
    mode = candidats["mode"] if "mode" in candidats else pd.Series("constructible", index=candidats.index)
    q = pd.DataFrame(index=candidats.index, columns=["q1", "med", "q3", "nb"], dtype=float)
    base = pd.Series(None, index=candidats.index, dtype=object)

    c = candidats[mode != "pari"]
    if len(c):
        q.loc[c.index] = _estimer(c, comparables(d.ventes, d.zones, cfg.get("typezones_comparables", [])), cfg)
        base.loc[c.index] = "terrains constructibles"
    c = candidats[mode == "pari"]
    if len(c):
        q.loc[c.index] = _estimer(c, comparables(d.ventes, d.zones, cfg.get("typezones_comparables_pari", [])), cfg)
        base.loc[c.index] = "terrains en zone AUs"
        manque = c.index[q.loc[c.index, "nb"].fillna(0) < cfg["ventes_min"]]
        if len(manque):
            secours = comparables(d.ventes, d.zones, cfg.get("typezones_comparables_pari_secours", []))
            q.loc[manque] = _estimer(candidats.loc[manque], secours, cfg)
            base.loc[manque] = "terrains AUs, agricoles et naturels (estimation basse)"

    q["nb"] = q["nb"].fillna(0)
    valide = q["nb"] >= cfg["ventes_min"]
    surface = candidats["surface_m2"].astype(float)
    out["prix_m2_median"] = q["med"].where(valide).astype(float).round(1)
    out["prix_nb_ventes"] = q["nb"].astype(int)
    out["prix_estime"] = (surface * q["med"]).where(valide).astype(float).round(-3)
    out["prix_estime_bas"] = (surface * q["q1"]).where(valide).astype(float).round(-3)
    out["prix_estime_haut"] = (surface * q["q3"]).where(valide).astype(float).round(-3)
    out["prix_base"] = base.where(valide)
    # Rang calculé à l'intérieur de chaque mode : un terrain AUs n'est pas comparé à un terrain urbain.
    note = pd.Series(np.nan, index=candidats.index)
    for m in mode.unique():
        idx = mode.index[mode == m]
        note.loc[idx] = rang(out.loc[idx, "prix_m2_median"], inverse=True)
    out["note_prix"] = note.fillna(NEUTRE).round(1)
    out["prix_dispo"] = valide
    return out
