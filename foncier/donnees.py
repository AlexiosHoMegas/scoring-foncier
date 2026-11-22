"""Conteneur des données d'entrée, communes au mode réel et au mode démo.

Toutes les couches géographiques sont en Lambert-93 (EPSG:2154).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import geopandas as gpd
import pandas as pd

from . import CRS_METRIQUE


def gdf_vide(colonnes: list[str] | None = None) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({c: [] for c in (colonnes or [])}, geometry=[], crs=CRS_METRIQUE)


@dataclass
class Donnees:
    # Obligatoires : sans elles, le pipeline s'arrête.
    communes: gpd.GeoDataFrame            # insee, nom, geometry
    parcelles: gpd.GeoDataFrame           # id, insee, contenance, geometry
    zones: gpd.GeoDataFrame               # typezone, libelle, formdomi, geometry
    # Facultatives : si absentes, l'agent concerné renvoie une note neutre.
    batiments: gpd.GeoDataFrame = field(default_factory=gdf_vide)
    prescriptions: gpd.GeoDataFrame = field(default_factory=gdf_vide)   # typepsc, libelle
    ppr: gpd.GeoDataFrame = field(default_factory=gdf_vide)             # périmètres PM1
    routes: gpd.GeoDataFrame = field(default_factory=gdf_vide)          # highway
    echangeurs: gpd.GeoDataFrame = field(default_factory=gdf_vide)      # points
    trafic: gpd.GeoDataFrame = field(default_factory=gdf_vide)          # tmja, pl_pct, annee
    ventes: gpd.GeoDataFrame = field(default_factory=gdf_vide)          # date, prix_m2, surface
    population: pd.DataFrame = field(default_factory=pd.DataFrame)      # insee, pop_recente, pop_ancienne, ecart_annees
    permis: gpd.GeoDataFrame = field(default_factory=gdf_vide)          # date, surface_m2
    centre: gpd.GeoDataFrame = field(default_factory=gdf_vide)
    # Disponibilité et propriété.
    proprietaires: pd.DataFrame = field(default_factory=pd.DataFrame)   # id, groupe, forme, denomination
    parcelles_vendues: pd.Series = field(default_factory=lambda: pd.Series(dtype=str))  # id -> date
    parcelles_permis: set = field(default_factory=set)                  # ids avec permis récent
    # Rareté foncière (consommation d'espaces), par commune.
    conso: pd.DataFrame = field(default_factory=pd.DataFrame)           # insee, m2_2011_2021, m2_2021_2025
    conso_grille: gpd.GeoDataFrame = field(default_factory=gdf_vide)    # carreaux 1 km : m2_recent, m2_ancien
    # Zonage publié la semaine précédente : typezone -> liste d'ids non constructibles.
    zonage_precedent: dict = field(default_factory=dict)
    # Suivi : état de chaque source, affiché dans la carte.
    sources: dict = field(default_factory=dict)
    demo: bool = False
