"""Agent Rareté : part du budget d'artificialisation déjà consommée par la commune.

La loi Climat et Résilience demande de diviser par deux, sur 2021-2031, la consommation
d'espaces naturels de 2011-2021. Une commune qui a déjà utilisé une grande part de ce budget
en 2021-2025 ouvrira peu de nouveaux terrains : le foncier déjà constructible y deviendra rare.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .outils import NEUTRE, rang


def noter(candidats, d, cfg) -> pd.DataFrame:
    out = pd.DataFrame(index=candidats.index)
    if d.conso.empty or candidats.empty:
        out["note_rarete"] = NEUTRE
        out["budget_zan_consomme_pct"] = np.nan
        out["rarete_dispo"] = False
        return out
    c = d.conso.set_index("insee")
    budget = c["m2_2011_2021"] / 2
    part = (100 * c["m2_2021_2025"] / budget.replace(0, np.nan)).clip(upper=500)
    territoire = part.reindex(d.communes["insee"])
    notes = rang(territoire)
    out["budget_zan_consomme_pct"] = candidats["insee"].map(territoire).round(0)
    out["note_rarete"] = candidats["insee"].map(notes).fillna(NEUTRE).round(1)
    out["rarete_dispo"] = candidats["insee"].map(territoire).notna()
    return out
