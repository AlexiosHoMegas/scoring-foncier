"""Propriétaires personnes morales des parcelles (DGFiP, data.economie.gouv.fr).

Le fichier ne contient que les parcelles détenues par une société, une association ou une
personne publique. Une parcelle absente appartient donc à un ou des particuliers (ou à une
entreprise individuelle). Les noms et colonnes exacts du fichier ne sont pas documentés de
façon stable : on repère les pièces jointes et les colonnes par leur nom.
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata
import zipfile

import pandas as pd

from ..http import get_json, telecharger

log = logging.getLogger(__name__)


def _normaliser(texte: str) -> str:
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().upper()


def _pieces_jointes(cfg: dict) -> list[str]:
    base = cfg["sources"]["personnes_morales"]
    meta = get_json(f"{base}/", cache=False)
    pieces = meta.get("attachments") or meta.get("metas", {}).get("attachments") or []
    choisies = []
    for p in pieces:
        nom = f"{p.get('id', '')} {p.get('title', '')}".lower()
        if "parcel" in nom and "descriptif" not in nom and ("zip" in nom or "csv" in nom or "txt" in nom):
            annee = max([int(a) for a in re.findall(r"20\d\d", nom)] or [0])
            choisies.append((annee, f"{base}/attachments/{p['id']}"))
    if not choisies:
        log.warning("Personnes morales : pièces jointes vues : %s", [p.get("id") for p in pieces][:30])
        raise ValueError("Aucun fichier de parcelles trouvé")
    plus_recente = max(a for a, _ in choisies)
    return [u for a, u in choisies if a == plus_recente]


def _colonne(colonnes: list[str], *mots: str, sauf: tuple[str, ...] = ()) -> str | None:
    for c in colonnes:
        n = _normaliser(c)
        if all(m in n for m in mots) and not any(s in n for s in sauf):
            return c
    return None


def lire_tableau(df: pd.DataFrame, deps: list[str]) -> pd.DataFrame:
    cols = list(df.columns)
    c_dep = _colonne(cols, "DEPARTEMENT")
    c_com = _colonne(cols, "COMMUNE", sauf=("NOM",))
    c_pre = _colonne(cols, "PREFIXE")
    c_sec = _colonne(cols, "SECTION", sauf=("PREFIXE",))
    c_plan = _colonne(cols, "PLAN")
    c_grp = _colonne(cols, "GROUPE")
    c_forme = _colonne(cols, "FORME JURIDIQUE", sauf=("ABREGEE",))
    c_abr = _colonne(cols, "FORME JURIDIQUE ABREGEE")
    c_nom = _colonne(cols, "DENOMINATION")
    manquantes = [n for n, c in [("département", c_dep), ("commune", c_com), ("section", c_sec),
                                 ("plan", c_plan), ("groupe", c_grp)] if c is None]
    if manquantes:
        raise ValueError(f"Colonnes introuvables : {manquantes} parmi {cols[:30]}")
    dep = df[c_dep].astype(str).str.strip().str.zfill(2)
    df = df[dep.isin(deps)].copy()
    dep = df[c_dep].astype(str).str.strip().str.zfill(2)
    com = df[c_com].astype(str).str.strip()
    insee = com.where(com.str.len() == 5, dep + com.str.zfill(3))
    prefixe = df[c_pre].fillna("").astype(str).str.strip().str.zfill(3) if c_pre else "000"
    section = df[c_sec].astype(str).str.strip().str.upper().str.zfill(2)
    plan = df[c_plan].astype(str).str.strip().str.replace(r"\D", "", regex=True).str.zfill(4)
    out = pd.DataFrame({
        "id": insee + prefixe + section + plan,
        "groupe": df[c_grp].astype(str).str.strip().str[:1],
        "forme": df[c_forme].astype(str).str.strip() if c_forme else None,
        "forme_abregee": df[c_abr].astype(str).str.strip() if c_abr else None,
        "denomination": df[c_nom].astype(str).str.strip() if c_nom else None,
    })
    # Une parcelle peut avoir plusieurs titulaires de droits : on garde le premier.
    return out.drop_duplicates("id").reset_index(drop=True)


def _lire_fichier(contenu: bytes, deps: list[str]) -> pd.DataFrame:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            brut = pd.read_csv(io.BytesIO(contenu), sep=";", dtype=str, encoding=enc)
            return lire_tableau(brut, deps)
        except UnicodeDecodeError:
            continue
    raise ValueError("Encodage du fichier non reconnu")


def charger(cfg: dict, deps: list[str]) -> pd.DataFrame:
    morceaux = []
    for url in _pieces_jointes(cfg):
        chemin = telecharger(url, ".bin")
        if zipfile.is_zipfile(chemin):
            with zipfile.ZipFile(chemin) as z:
                for nom in z.namelist():
                    if nom.lower().endswith((".csv", ".txt")):
                        morceaux.append(_lire_fichier(z.read(nom), deps))
        else:
            morceaux.append(_lire_fichier(chemin.read_bytes(), deps))
    df = pd.concat(morceaux, ignore_index=True) if morceaux else pd.DataFrame()
    if df.empty:
        raise ValueError("Aucune parcelle de personne morale pour le territoire")
    return df.drop_duplicates("id").reset_index(drop=True)
