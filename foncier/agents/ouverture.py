"""Agent Ouverture : chances qu'une zone AUs soit ouverte à la construction.

Deux indices simples :
- contiguïté : une zone AUs collée à la ville existante (zone U) s'ouvre en général en premier ;
- marge ZAN : une commune qui a encore une bonne part de son budget d'artificialisation
  2021-2031 peut ouvrir de nouvelles zones ; une commune qui l'a épuisé ne le pourra guère.
Les parcelles déjà constructibles reçoivent 100.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .outils import NEUTRE, lineaire_decroissant


def noter(candidats, d, cfg) -> pd.DataFrame:
    out = pd.DataFrame(index=candidats.index)
    out["note_ouverture"] = 100.0
    out["dist_zone_urbaine_m"] = np.nan
    mode = candidats["mode"] if "mode" in candidats else pd.Series("constructible", index=candidats.index)
    pari = candidats[mode == "pari"]
    if pari.empty:
        return out
    urbaines = d.zones[d.zones["typezone"] == "U"]
    if urbaines.empty:
        contiguite = pd.Series(NEUTRE, index=pari.index)
    else:
        limite = urbaines.geometry.union_all()
        dist = pari.geometry.distance(limite)
        out.loc[pari.index, "dist_zone_urbaine_m"] = dist.round(0)
        contiguite = lineaire_decroissant(dist, cfg["distance_ideale_m"], cfg["distance_max_m"])
    marge = pd.Series(NEUTRE, index=pari.index)
    if not d.conso.empty:
        c = d.conso.set_index("insee")
        consomme = (100 * c["m2_2021_2025"] / (c["m2_2011_2021"] / 2).replace(0, np.nan)).clip(0, 100)
        marge = (100 - pari["insee"].map(consomme)).fillna(NEUTRE)
    w = cfg["part_contiguite"]
    out.loc[pari.index, "note_ouverture"] = (w * contiguite + (1 - w) * marge).round(1)
    return out
