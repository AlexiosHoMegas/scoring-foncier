"""Agent Front d'urbanisation : la ville grandit-elle autour de la parcelle ?

On additionne les surfaces nouvellement urbanisées ces 6 dernières années dans les carreaux
de 1 km situés à moins de 2 km (données Cerema). Une parcelle sur le front d'urbanisation
le plus actif obtient la meilleure note : c'est là que la ville avance le plus vite.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shapely

from .outils import NEUTRE, rang


def noter(candidats, d, cfg) -> pd.DataFrame:
    out = pd.DataFrame(index=candidats.index)
    if d.conso_grille.empty or candidats.empty:
        out["note_front"] = NEUTRE
        out["urbanise_recent_ha"] = np.nan
        out["front_dispo"] = False
        return out
    pts = candidats.geometry.representative_point().values
    arbre = shapely.STRtree(d.conso_grille.geometry.values)
    i_c, i_g = arbre.query(pts, predicate="dwithin", distance=cfg["rayon_m"])
    recent = d.conso_grille["m2_recent"].to_numpy()[i_g]
    somme = pd.Series(recent).groupby(i_c).sum().reindex(range(len(pts))).fillna(0)
    somme.index = candidats.index
    out["urbanise_recent_ha"] = (somme / 10000).round(1)
    out["note_front"] = rang(np.log1p(somme)).fillna(NEUTRE).round(1)
    out["front_dispo"] = True
    return out
