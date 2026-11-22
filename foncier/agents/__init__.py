"""Six agents indépendants, chacun note les parcelles candidates de 0 à 100.

Chaque agent renvoie un DataFrame indexé comme les candidates, avec au moins
une colonne `note_<agent>`. Une colonne `<agent>_dispo` vaut False quand la donnée
manquait : la note est alors neutre (50) et signalée dans la carte.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import pandas as pd

from ..donnees import Donnees
from . import accessibilite, developpement, dynamique, front, ouverture, prix, rarete, surface, trafic

log = logging.getLogger(__name__)

REGISTRE = {
    "prix": prix.noter,
    "trafic": trafic.noter,
    "accessibilite": accessibilite.noter,
    "surface": surface.noter,
    "dynamique": dynamique.noter,
    "developpement": developpement.noter,
    "rarete": rarete.noter,
    "ouverture": ouverture.noter,
    "front": front.noter,
}


def executer(candidats: gpd.GeoDataFrame, d: Donnees, cfg: dict) -> pd.DataFrame:
    resultats = {}
    cfg_agents = {nom: dict(cfg["agents"].get(nom, {})) for nom in REGISTRE}
    cfg_agents["surface"].setdefault("minimum_m2", cfg["filtres"]["surface_min_m2"])
    with ThreadPoolExecutor(max_workers=len(REGISTRE)) as pool:
        futurs = {nom: pool.submit(f, candidats, d, cfg_agents[nom]) for nom, f in REGISTRE.items()}
        for nom, futur in futurs.items():
            res = futur.result()
            n = res[f"note_{nom}"]
            if n.isna().any() or (n < 0).any() or (n > 100).any():
                raise ValueError(f"Agent {nom} : notes hors de [0, 100]")
            resultats[nom] = res
            log.info("Agent %-14s : moyenne %.1f", nom, n.mean() if len(n) else float("nan"))
    return pd.concat(resultats.values(), axis=1)
