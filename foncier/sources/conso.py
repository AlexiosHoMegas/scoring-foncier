"""Consommation d'espaces naturels, agricoles et forestiers par commune (Cerema, en m²).

Colonnes vérifiées : idcom, naf11art21 (2011-2021), naf21art25 (2021-2025).
"""
from __future__ import annotations

import pandas as pd

from ..http import telecharger


def lire(chemin, communes: list[str]) -> pd.DataFrame:
    df = pd.read_csv(chemin, sep=None, engine="python", dtype={"idcom": str},
                     usecols=["idcom", "naf11art21", "naf21art25"])
    df = df[df["idcom"].isin(communes)]
    return df.rename(columns={"idcom": "insee", "naf11art21": "m2_2011_2021",
                              "naf21art25": "m2_2021_2025"}).reset_index(drop=True)


def charger(cfg: dict, communes: list[str]) -> pd.DataFrame:
    df = lire(telecharger(cfg["sources"]["consoenaf"], ".csv"), communes)
    if df.empty:
        raise ValueError("Communes absentes du fichier de consommation d'espaces")
    return df
