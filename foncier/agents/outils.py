from __future__ import annotations

import numpy as np
import pandas as pd

NEUTRE = 50.0


def rang(serie: pd.Series, inverse: bool = False) -> pd.Series:
    """Rang centile de 0 à 100 ; les valeurs manquantes restent manquantes."""
    valides = serie.dropna()
    if len(valides) <= 1:
        return pd.Series(np.where(serie.notna(), NEUTRE, np.nan), index=serie.index)
    r = valides.rank(method="average", pct=True)
    r = (r - r.min()) / (r.max() - r.min()) if r.max() > r.min() else r * 0 + 0.5
    if inverse:
        r = 1 - r
    return (r * 100).reindex(serie.index)


def lineaire_decroissant(x: pd.Series, ideal: float, maximum: float) -> pd.Series:
    """100 en dessous de `ideal`, 0 au-delà de `maximum`, linéaire entre les deux."""
    return (100 * (maximum - x) / (maximum - ideal)).clip(0, 100)


def log_croissant(x: pd.Series, minimum: float, reference: float) -> pd.Series:
    """0 sous `minimum`, 100 à partir de `reference`, échelle logarithmique entre les deux."""
    x = x.clip(lower=minimum)
    return (100 * np.log(x / minimum) / np.log(reference / minimum)).clip(0, 100)
