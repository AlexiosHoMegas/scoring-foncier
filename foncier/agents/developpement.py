"""Agent Développement : surface de locaux autorisée récemment autour de la parcelle."""
from __future__ import annotations

import numpy as np
import pandas as pd
import shapely

from .outils import NEUTRE, rang


def noter(candidats, d, cfg) -> pd.DataFrame:
    out = pd.DataFrame(index=candidats.index)
    if d.permis.empty or candidats.empty:
        out["note_developpement"] = NEUTRE
        out["locaux_autorises_m2"] = np.nan
        out["developpement_dispo"] = False
        return out
    pts = candidats.geometry.representative_point().values
    arbre = shapely.STRtree(d.permis.geometry.values)
    i_c, i_p = arbre.query(pts, predicate="dwithin", distance=cfg["rayon_m"])
    surf = d.permis["surface_m2"].to_numpy()[i_p]
    somme = pd.Series(surf).groupby(i_c).sum().reindex(range(len(pts))).fillna(0)
    somme.index = candidats.index
    out["locaux_autorises_m2"] = somme.round(0)
    out["note_developpement"] = rang(np.log1p(somme)).fillna(NEUTRE).round(1)
    out["developpement_dispo"] = True
    return out
