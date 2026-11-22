"""Jeu de données fictif, reproductible, pour tester le pipeline et la carte hors ligne.

Les communes portent des codes INSEE inexistants (99xxx) et la carte affiche un bandeau
« données fictives » : rien ici ne décrit un terrain réel.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, box

from . import CRS_METRIQUE, CRS_WEB
from .donnees import Donnees

BLOC = 200.0
COTE = 4000.0


def generer(cfg: dict, graine: int = 42) -> Donnees:
    rng = np.random.default_rng(graine)
    c = cfg["territoire"]["centre"]
    centre = gpd.GeoDataFrame(geometry=[Point(c["lon"], c["lat"])], crs=CRS_WEB).to_crs(CRS_METRIQUE)
    cx, cy = centre.geometry.iloc[0].x, centre.geometry.iloc[0].y
    x0, y0 = cx + 6000, cy - 8000  # territoire fictif à l'est du centre

    communes, parcelles, zones = [], [], []
    for k, nom in enumerate(["Démo-Est", "Démo-Centre", "Démo-Ouest"]):
        insee = f"9900{k + 1}"
        ox = x0 + k * COTE
        communes.append({"insee": insee, "nom": nom, "geometry": box(ox, y0, ox + COTE, y0 + COTE)})
        # Bandes de zonage, de l'activité au naturel.
        limites = np.cumsum(rng.dirichlet(np.ones(6)) * COTE)
        types = [("U", "UE", "0201"), ("U", "UB", "0100"), ("AUc", "AU1", "0200"),
                 ("AUs", "AU0", None), ("A", "A", None), ("N", "N", None)]
        gauche = ox
        for (typezone, libelle, formdomi), lim in zip(types, limites):
            zones.append({"typezone": typezone, "libelle": libelle, "formdomi": formdomi,
                          "urlfic": None, "partition": "DEMO", "geometry": box(gauche, y0, ox + lim, y0 + COTE)})
            gauche = ox + lim
        n = 0
        for i in range(int(COTE / BLOC)):
            for j in range(int(COTE / BLOC)):
                bx, by = ox + i * BLOC, y0 + j * BLOC
                decoupe = rng.choice([1, 2, 4], p=[0.12, 0.38, 0.5])
                pas = BLOC / decoupe
                for a in range(decoupe):
                    for b in range(decoupe):
                        n += 1
                        geom = box(bx + a * pas, by + b * pas, bx + (a + 1) * pas, by + (b + 1) * pas)
                        parcelles.append({"id": f"{insee}000DM{n:04d}"[:14], "insee": insee,
                                          "contenance": geom.area, "geometry": geom})

    communes = gpd.GeoDataFrame(communes, crs=CRS_METRIQUE)
    parcelles = gpd.GeoDataFrame(parcelles, crs=CRS_METRIQUE)
    parcelles["id"] = parcelles["insee"] + "000DM" + parcelles.groupby("insee").cumcount().astype(str).str.zfill(4)
    zones = gpd.GeoDataFrame(zones, crs=CRS_METRIQUE)
    xmin, ymin, xmax, ymax = communes.total_bounds

    # Bâti sur 30 % des parcelles.
    tirage = parcelles.sample(frac=0.3, random_state=graine)
    batiments = gpd.GeoDataFrame({"insee": tirage["insee"]},
                                 geometry=tirage.geometry.scale(0.6, 0.6), crs=CRS_METRIQUE)

    # Routes : grille locale tous les 400 m, une départementale, une nationale, une autoroute.
    routes = []
    for x in np.arange(xmin, xmax + 1, 400):
        routes.append({"highway": "residential", "geometry": LineString([(x, ymin), (x, ymax)])})
    for y in np.arange(ymin, ymax + 1, 400):
        routes.append({"highway": "residential", "geometry": LineString([(xmin, y), (xmax, y)])})
    y_dep, x_nat = ymin + 2000, xmin + 6000
    routes.append({"highway": "secondary", "geometry": LineString([(xmin, y_dep), (xmax, y_dep)])})
    routes.append({"highway": "trunk", "geometry": LineString([(x_nat, ymin), (x_nat, ymax)])})
    routes.append({"highway": "motorway", "geometry": LineString([(xmin, ymin - 300), (xmax, ymin - 300)])})
    routes = gpd.GeoDataFrame(routes, crs=CRS_METRIQUE)
    echangeurs = gpd.GeoDataFrame({"nom": ["Échangeur démo 1", "Échangeur démo 2"]},
                                  geometry=[Point(xmin + 1500, ymin - 300), Point(xmin + 9000, ymin - 300)],
                                  crs=CRS_METRIQUE)
    trafic = gpd.GeoDataFrame({"compteur": ["DEMO.1", "DEMO.2"], "tmja": [14000, 4500],
                               "pl_pct": [8.0, 4.0], "annee": [2025, 2025], "source": "démo"},
                              geometry=[LineString([(xmin, y_dep), (xmax, y_dep)]),
                                        LineString([(xmin + 2000, ymin), (xmin + 2000, ymax)])],
                              crs=CRS_METRIQUE)

    prescriptions = gpd.GeoDataFrame({"typepsc": ["01", "05"], "libelle": ["EBC démo", "ER démo"]},
                                     geometry=[box(xmin + 500, ymin + 2500, xmin + 1100, ymin + 3100),
                                               box(xmin + 4000, ymin + 1000, xmin + 4400, ymin + 3000)],
                                     crs=CRS_METRIQUE)
    ppr = gpd.GeoDataFrame(geometry=[box(xmin + 7000, ymin, xmin + 8200, ymin + 1200)], crs=CRS_METRIQUE)

    # Ventes de terrains : prix décroissant avec l'éloignement du centre.
    n = 500
    xs, ys = rng.uniform(xmin - 2000, xmax + 2000, n), rng.uniform(ymin - 2000, ymax + 2000, n)
    dist = np.hypot(xs - cx, ys - cy)
    prix = (25 + 160 * np.exp(-dist / 12000)) * rng.lognormal(0, 0.25, n)
    ventes = gpd.GeoDataFrame({"id_mutation": [f"DEMO-{i}" for i in range(n)], "date": "2025-06-01",
                               "prix_m2": prix.round(1), "surface": rng.uniform(500, 20000, n).round()},
                              geometry=gpd.points_from_xy(xs, ys), crs=CRS_METRIQUE)

    population = pd.DataFrame({"insee": communes["insee"], "pop_recente": [5200, 12800, 3100],
                               "pop_ancienne": [4300, 12100, 3050], "ecart_annees": 10, "annee_recente": 2023})

    m = 70
    permis = gpd.GeoDataFrame({"date": "2024-03-01", "surface_m2": rng.lognormal(7, 1, m).round()},
                              geometry=gpd.points_from_xy(rng.uniform(xmin, xmin + 6000, m),
                                                          rng.uniform(ymin, ymax, m)), crs=CRS_METRIQUE)

    # Propriétaires : quelques communes et sociétés, le reste à des particuliers.
    echantillon = parcelles.sample(frac=0.15, random_state=graine + 1)
    groupes = rng.choice(["4", "0", "0", "6", "1"], len(echantillon))
    noms = {"4": "COMMUNE DE DÉMO", "0": "SCI DÉMO FONCIER", "6": "SEM DÉMO AMÉNAGEMENT", "1": "ÉTAT"}
    formes = {"4": "Commune", "0": "Société civile immobilière", "6": "Société d'économie mixte", "1": "État"}
    proprietaires = pd.DataFrame({"id": echantillon["id"].to_numpy(), "groupe": groupes,
                                  "forme": [formes[g] for g in groupes], "forme_abregee": None,
                                  "denomination": [noms[g] for g in groupes]})
    vendues = pd.Series("2025-09-01", index=parcelles.sample(frac=0.04, random_state=graine + 2)["id"].to_numpy())
    permis_ids = set(parcelles.sample(frac=0.03, random_state=graine + 3)["id"])
    conso = pd.DataFrame({"insee": communes["insee"], "m2_2011_2021": [400000, 250000, 90000],
                          "m2_2021_2025": [150000, 40000, 50000]})
    # Zonage « de la semaine dernière » : une partie de la zone AUc était encore en AUs.
    auc = zones[zones["typezone"] == "AUc"].geometry.union_all()
    dans_auc = parcelles[parcelles.geometry.representative_point().within(auc)]
    precedent = {"AUs": sorted(dans_auc.sample(frac=0.1, random_state=graine + 4)["id"])}

    etats = {nom: {"etat": "démo"} for nom in
             ["communes", "cadastre_parcelles", "cadastre_batiments", "plu_zones", "plu_prescriptions",
              "ppr", "osm", "trafic_cd34", "dvf", "insee_population", "sitadel", "sitadel_parcelles",
              "proprietaires", "consommation_espaces", "zonage_precedent"]}
    return Donnees(communes=communes, parcelles=parcelles, zones=zones, batiments=batiments,
                   prescriptions=prescriptions, ppr=ppr, routes=routes, echangeurs=echangeurs,
                   trafic=trafic, ventes=ventes, population=population, permis=permis,
                   centre=centre, proprietaires=proprietaires, parcelles_vendues=vendues,
                   parcelles_permis=permis_ids, conso=conso, zonage_precedent=precedent,
                   sources=etats, demo=True)
