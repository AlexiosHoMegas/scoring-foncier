"""Agent Dynamique : croissance démographique de la commune."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .outils import NEUTRE, rang


def noter(candidats, d, cfg) -> pd.DataFrame:
    out = pd.DataFrame(index=candidats.index)
    if d.population.empty or candidats.empty:
        out["note_dynamique"] = NEUTRE
        out["croissance_pop_an_pct"] = np.nan
        out["dynamique_dispo"] = False
        return out
    pop = d.population.set_index("insee")
    taux = ((pop["pop_recente"] / pop["pop_ancienne"]) ** (1 / pop["ecart_annees"]) - 1) * 100
    territoire = taux.reindex(d.communes["insee"])
    notes_communes = rang(territoire)
    insee = candidats["insee"]
    out["croissance_pop_an_pct"] = insee.map(territoire).round(2)
    out["note_dynamique"] = insee.map(notes_communes).fillna(NEUTRE).round(1)
    out["dynamique_dispo"] = insee.map(territoire).notna()
    return out
