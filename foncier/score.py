from __future__ import annotations

import numpy as np
import pandas as pd

from .config import AGENTS


def _penalites(candidats: pd.DataFrame, cfg: dict) -> np.ndarray:
    pen = cfg.get("penalites", {})
    m = np.ones(len(candidats))
    m *= np.where(candidats["residentiel"].to_numpy(dtype=bool), pen.get("residentiel", 1.0), 1.0)
    m *= np.where(candidats["ppr"].to_numpy(dtype=bool), pen.get("ppr", 1.0), 1.0)
    return m


def calculer(notes: pd.DataFrame, candidats: pd.DataFrame, cfg: dict, poids: dict | None = None) -> pd.Series:
    poids = poids or cfg["poids"]
    w = np.array([float(poids.get(a, 0)) for a in AGENTS])
    matrice = notes[[f"note_{a}" for a in AGENTS]].to_numpy(dtype=float)
    score = matrice @ (w / w.sum()) * _penalites(candidats, cfg)
    return pd.Series(score, index=notes.index).clip(0, 100).round(1)


def robustesse(notes: pd.DataFrame, candidats: pd.DataFrame, cfg: dict, graine: int = 0) -> pd.Series:
    """Part des tirages de poids (autour des poids choisis) où la parcelle reste dans le top N %.

    Une parcelle à 90 % reste en tête quels que soient les réglages raisonnables ; à 20 %,
    elle ne gagne qu'avec des poids bien précis.
    """
    r = cfg.get("robustesse", {})
    tirages, conc, top = r.get("tirages", 500), r.get("concentration", 40), r.get("top_pct", 10)
    if len(notes) == 0:
        return pd.Series(dtype=float)
    w0 = np.array([float(cfg["poids"].get(a, 0)) for a in AGENTS]) / 100
    alpha = np.maximum(w0 * conc, 0.05)
    poids = np.random.default_rng(graine).dirichlet(alpha, tirages)           # tirages x agents
    matrice = notes[[f"note_{a}" for a in AGENTS]].to_numpy(dtype=float)       # parcelles x agents
    scores = (matrice @ poids.T) * _penalites(candidats, cfg)[:, None]          # parcelles x tirages
    seuil = np.percentile(scores, 100 - top, axis=0)
    part = (scores >= seuil).mean(axis=1) * 100
    return pd.Series(part, index=notes.index).round(0)


def classe(score: float) -> str:
    if score >= 75:
        return "acheter"
    if score >= 60:
        return "intéressant"
    if score >= 40:
        return "à étudier"
    return "éviter"
