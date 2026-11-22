"""Agent Accessibilité : proximité d'un échangeur autoroutier et du centre."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .outils import NEUTRE, lineaire_decroissant


def noter(candidats, d, cfg) -> pd.DataFrame:
    out = pd.DataFrame(index=candidats.index)
    if candidats.empty:
        out["note_accessibilite"] = pd.Series(dtype=float)
        return out
    pts = candidats.geometry.representative_point()
    detour = cfg["detour"]
    if d.echangeurs.empty:
        dist_ech = pd.Series(np.nan, index=candidats.index)
        note_ech = pd.Series(NEUTRE, index=candidats.index)
    else:
        dist_ech = pts.apply(lambda p: d.echangeurs.distance(p).min()) * detour
        note_ech = lineaire_decroissant(dist_ech, cfg["echangeur_ideal_m"], cfg["echangeur_max_m"])
    centre = d.centre.geometry.iloc[0]
    dist_centre = pts.distance(centre) * detour
    note_centre = lineaire_decroissant(dist_centre, cfg["centre_ideal_m"], cfg["centre_max_m"])
    w = cfg["part_echangeur"]
    out["note_accessibilite"] = (w * note_ech + (1 - w) * note_centre).round(1)
    out["dist_echangeur_km"] = (dist_ech / 1000).round(1)
    out["dist_centre_km"] = (dist_centre / 1000).round(1)
    out["accessibilite_dispo"] = not d.echangeurs.empty
    return out
