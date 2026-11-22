"""Ventes de terrains nus issues de DVF géolocalisées."""
from __future__ import annotations

import logging
import re
from datetime import date

import geopandas as gpd
import pandas as pd

from .. import CRS_METRIQUE, CRS_WEB
from ..http import get_json, telecharger

log = logging.getLogger(__name__)

COLONNES = ["id_mutation", "date_mutation", "nature_mutation", "valeur_fonciere", "code_departement",
            "id_parcelle", "type_local", "nature_culture", "surface_terrain", "longitude", "latitude"]
NATURES = {"Vente", "Vente terrain à bâtir", "Adjudication"}


def _fichiers(cfg: dict, annees: list[int]) -> list[str]:
    """Trouve les fichiers annuels via l'API data.gouv ; sinon le fichier 5 ans de secours."""
    try:
        meta = get_json(f"{cfg['sources']['datagouv_api']}/datasets/{cfg['sources']['dvf_dataset']}/",
                        cache=False)
        urls = []
        for r in meta.get("resources", []):
            titre = f"{r.get('title', '')} {r.get('url', '')}"
            if not re.search(r"\.csv(\.gz)?", titre, re.I):
                continue
            trouves = {int(a) for a in re.findall(r"20\d\d", r.get("title", ""))}
            if len(trouves) == 1 and trouves.pop() in annees:
                urls.append(r["url"])
        if urls:
            return urls
    except Exception as e:  # noqa: BLE001
        log.warning("API data.gouv indisponible pour DVF (%s), fichier de secours", e)
    return [cfg["sources"]["dvf_secours"]]


def ventes_terrains(cfg: dict, deps: list[str]) -> gpd.GeoDataFrame:
    n = cfg["agents"]["prix"]["annees"]
    aujourd_hui = date.today()
    annees = list(range(aujourd_hui.year - n, aujourd_hui.year + 1))
    debut = f"{aujourd_hui.year - n}-{aujourd_hui.month:02d}-01"
    morceaux = []
    for url in _fichiers(cfg, annees):
        chemin = telecharger(url, ".csv.gz")
        for bloc in pd.read_csv(chemin, usecols=lambda c: c in COLONNES, dtype=str, chunksize=500_000,
                                compression="gzip"):
            bloc = bloc[bloc["code_departement"].isin(deps) & bloc["nature_mutation"].isin(NATURES)
                        & (bloc["date_mutation"] >= debut)]
            if not bloc.empty:
                morceaux.append(bloc)
    if not morceaux:
        raise ValueError("Aucune vente DVF trouvée pour le territoire")
    df = pd.concat(morceaux, ignore_index=True)
    for c in ("valeur_fonciere", "surface_terrain", "longitude", "latitude"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Une mutation = une vente. On garde les ventes sans aucun local (terrain nu).
    bati = df.groupby("id_mutation")["type_local"].apply(lambda s: s.notna().any())
    df = df[df["id_mutation"].isin(bati[~bati].index)]
    surfaces = df.drop_duplicates(["id_mutation", "id_parcelle", "nature_culture"]) \
        .groupby("id_mutation")["surface_terrain"].sum()
    ventes = df.groupby("id_mutation").agg(date=("date_mutation", "first"),
                                           valeur=("valeur_fonciere", "first"),
                                           lon=("longitude", "mean"), lat=("latitude", "mean"))
    ventes["surface"] = surfaces
    ventes = ventes.dropna(subset=["valeur", "surface", "lon", "lat"])
    ventes = ventes[ventes["surface"] >= 200]
    ventes["prix_m2"] = ventes["valeur"] / ventes["surface"]
    # Retire les montants symboliques et les erreurs de saisie évidentes.
    ventes = ventes[(ventes["prix_m2"] >= 1) & (ventes["prix_m2"] <= 3000)]
    g = gpd.GeoDataFrame(ventes.reset_index(), geometry=gpd.points_from_xy(ventes["lon"], ventes["lat"]),
                         crs=CRS_WEB).to_crs(CRS_METRIQUE)
    return g[["id_mutation", "date", "prix_m2", "surface", "geometry"]]
