from __future__ import annotations

import pandas as pd

from .config import AGENTS


def calculer(notes: pd.DataFrame, candidats: pd.DataFrame, cfg: dict) -> pd.Series:
    poids = {a: float(cfg["poids"].get(a, 0)) for a in AGENTS}
    total = sum(poids.values())
    score = sum(notes[f"note_{a}"] * w for a, w in poids.items()) / total
    pen = cfg.get("penalites", {})
    score = score * candidats["residentiel"].map({True: pen.get("residentiel", 1.0), False: 1.0})
    score = score * candidats["ppr"].map({True: pen.get("ppr", 1.0), False: 1.0})
    return score.clip(0, 100).round(1)


def classe(score: float) -> str:
    if score >= 75:
        return "acheter"
    if score >= 60:
        return "intéressant"
    if score >= 40:
        return "à étudier"
    return "éviter"
