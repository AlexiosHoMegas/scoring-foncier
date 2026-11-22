from __future__ import annotations

from pathlib import Path

import yaml

AGENTS = ["prix", "trafic", "accessibilite", "surface", "dynamique", "developpement", "rarete", "ouverture", "front"]


def charger(chemin: str | Path) -> dict:
    with open(chemin, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    poids = cfg.get("poids", {})
    inconnus = set(poids) - set(AGENTS)
    if inconnus:
        raise ValueError(f"Poids pour des agents inconnus : {sorted(inconnus)}")
    if sum(poids.get(a, 0) for a in AGENTS) <= 0:
        raise ValueError("La somme des poids doit être positive")
    for nom, profil in cfg.get("profils", {}).items():
        if set(profil["poids"]) - set(AGENTS) or sum(profil["poids"].values()) <= 0:
            raise ValueError(f"Profil {nom} : poids invalides")
    return cfg
