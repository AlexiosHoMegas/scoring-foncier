"""Historique des populations communales (INSEE)."""
from __future__ import annotations

import re
from urllib.parse import urljoin

import pandas as pd

from ..http import get_texte, telecharger


def _url_fichier(page: str) -> str:
    html = get_texte(page)
    liens = re.findall(r'href="([^"]*base-pop-historiques[^"]*\.xlsx)"', html)
    if not liens:
        raise ValueError("Lien du fichier INSEE introuvable sur la page")
    return urljoin(page, sorted(liens)[-1])


def lire(chemin, ecart: int) -> pd.DataFrame:
    brut = pd.read_excel(chemin, sheet_name=0, header=None, dtype=str)
    ligne = brut.index[brut.apply(lambda r: r.astype(str).str.upper().eq("CODGEO").any(), axis=1)][0]
    df = brut.iloc[ligne + 1:].copy()
    df.columns = brut.iloc[ligne].astype(str).str.upper()
    annees = {}
    for c in df.columns:
        m = re.fullmatch(r"(PMUN|PSDC|PTOT)(\d{4})", c)
        if m:
            annees.setdefault(int(m.group(2)), c)
    if not annees:
        raise ValueError("Colonnes de population introuvables")
    recente = max(annees)
    candidates = [a for a in annees if a <= recente - ecart] or [min(annees)]
    ancienne = max(candidates)
    out = pd.DataFrame({
        "insee": df["CODGEO"].astype(str).str.zfill(5),
        "pop_recente": pd.to_numeric(df[annees[recente]], errors="coerce"),
        "pop_ancienne": pd.to_numeric(df[annees[ancienne]], errors="coerce"),
    })
    out["ecart_annees"] = recente - ancienne
    out["annee_recente"] = recente
    return out.dropna(subset=["pop_recente", "pop_ancienne"]).reset_index(drop=True)


def population(cfg: dict) -> pd.DataFrame:
    url = _url_fichier(cfg["sources"]["insee_population"])
    return lire(telecharger(url, ".xlsx"), cfg["agents"]["dynamique"]["annees"])
