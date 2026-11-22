"""Agent Prix : plus le foncier alentour est bon marché, plus la note est haute."""
from __future__ import annotations

import numpy as np
import pandas as pd
import shapely

from .outils import NEUTRE, rang


def _medianes(points, ventes, rayon: float) -> tuple[pd.Series, pd.Series]:
    arbre = shapely.STRtree(ventes.geometry.values)
    i_cand, i_vente = arbre.query(points.values, predicate="dwithin", distance=rayon)
    prix = ventes["prix_m2"].to_numpy()
    df = pd.DataFrame({"c": i_cand, "p": prix[i_vente]})
    g = df.groupby("c")["p"]
    return g.median(), g.size()


def noter(candidats, d, cfg) -> pd.DataFrame:
    out = pd.DataFrame(index=candidats.index)
    if d.ventes.empty or candidats.empty:
        out["note_prix"] = NEUTRE
        out["prix_dispo"] = False
        out["prix_m2_median"] = np.nan
        out["prix_nb_ventes"] = 0
        return out
    points = candidats.geometry.representative_point().reset_index(drop=True)
    med, nb = _medianes(points, d.ventes, cfg["rayon_m"])
    med = med.reindex(range(len(points)))
    nb = nb.reindex(range(len(points))).fillna(0)
    # Pas assez de ventes : on élargit le rayon.
    faibles = nb[nb < cfg["ventes_min"]].index
    if len(faibles):
        med2, nb2 = _medianes(points.iloc[faibles].reset_index(drop=True), d.ventes, cfg["rayon_max_m"])
        med2.index = faibles[med2.index]
        nb2.index = faibles[nb2.index]
        med.loc[med2.index] = med2
        nb.loc[nb2.index] = nb2
    med.index = nb.index = candidats.index
    valide = nb >= cfg["ventes_min"]
    out["prix_m2_median"] = med.where(valide).round(1)
    out["prix_nb_ventes"] = nb.astype(int)
    out["note_prix"] = rang(out["prix_m2_median"], inverse=True).fillna(NEUTRE).round(1)
    out["prix_dispo"] = valide
    return out
