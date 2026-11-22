"""Chargement des données réelles depuis les sources ouvertes."""
from __future__ import annotations

import logging
import traceback

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point

from .. import CRS_METRIQUE, CRS_WEB
from ..donnees import Donnees, gdf_vide
from ..http import get_json
from . import cadastre, conso, dvf, insee, osm, plu, proprietaires, sitadel, territoire, trafic

log = logging.getLogger(__name__)


def _essayer(nom: str, etats: dict, fonction, *args, defaut=None, obligatoire=False):
    try:
        resultat = fonction(*args)
        principal = resultat[0] if isinstance(resultat, tuple) else resultat
        taille = len(principal) if hasattr(principal, "__len__") else None
        etats[nom] = {"etat": "ok", "lignes": taille}
        log.info("Source %s : ok (%s lignes)", nom, taille)
        return resultat
    except Exception as e:  # noqa: BLE001 - on veut tout capturer pour les sources facultatives
        etats[nom] = {"etat": "erreur", "message": f"{type(e).__name__}: {e}"}
        log.error("Source %s : échec\n%s", nom, traceback.format_exc())
        if obligatoire:
            raise
        return defaut if defaut is not None else gdf_vide()


def charger(cfg: dict) -> Donnees:
    etats: dict = {}
    communes = _essayer("communes", etats, territoire.communes, cfg, obligatoire=True)
    parcelles = _essayer("cadastre_parcelles", etats, cadastre.couche, cfg, communes, "parcelles",
                         obligatoire=True)
    batiments = _essayer("cadastre_batiments", etats, cadastre.couche, cfg, communes, "batiments")
    zones = _essayer("plu_zones", etats, plu.zones, cfg, communes, obligatoire=True)
    prescriptions = _essayer("plu_prescriptions", etats, plu.prescriptions, cfg, communes)
    ppr = _essayer("ppr", etats, plu.ppr, cfg, communes)
    routes, echangeurs = _essayer("osm", etats, osm.routes_et_echangeurs, cfg, communes,
                                  defaut=(gdf_vide(["highway"]), gdf_vide()))
    trafic_ = _essayer("trafic_cd34", etats, trafic.sections, cfg)
    deps = sorted(set(communes["insee"].str[:2]))
    ventes, vendues = _essayer("dvf", etats, dvf.ventes_terrains, cfg, deps,
                               defaut=(gdf_vide(), pd.Series(dtype=str)))
    population = _essayer("insee_population", etats, insee.population, cfg, defaut=pd.DataFrame())
    permis = _essayer("sitadel", etats, sitadel.permis_locaux, cfg, deps, parcelles, communes)
    avec_permis = _essayer("sitadel_parcelles", etats, sitadel.parcelles_avec_permis, cfg, deps, defaut=set())
    proprios = _essayer("proprietaires", etats, proprietaires.charger, cfg, deps, defaut=pd.DataFrame())
    conso_ = _essayer("consommation_espaces", etats, conso.charger, cfg, list(communes["insee"]),
                      defaut=pd.DataFrame())
    precedent = _essayer("zonage_precedent", etats, zonage_precedent, cfg, defaut={})
    grille = _essayer("consommation_grille_1km", etats, conso.grille, cfg, communes)

    c = cfg["territoire"]["centre"]
    centre = gpd.GeoDataFrame(geometry=[Point(c["lon"], c["lat"])], crs=CRS_WEB).to_crs(CRS_METRIQUE)
    return Donnees(communes=communes, parcelles=parcelles, zones=zones, batiments=batiments,
                   prescriptions=prescriptions, ppr=ppr, routes=routes, echangeurs=echangeurs,
                   trafic=trafic_, ventes=ventes, population=population, permis=permis,
                   centre=centre, proprietaires=proprios, parcelles_vendues=vendues,
                   parcelles_permis=avec_permis, conso=conso_, conso_grille=grille, zonage_precedent=precedent,
                   sources=etats, demo=False)


def zonage_precedent(cfg: dict) -> dict:
    """Zonage publié la semaine précédente ; vide au premier lancement."""
    url = cfg["sources"].get("publication_precedente")
    if not url:
        return {}
    try:
        return get_json(url, cache=False).get("non_constructibles", {})
    except requests.HTTPError as e:
        if getattr(e.response, "status_code", None) == 404:
            log.info("Pas de publication précédente : premier lancement")
            return {}
        raise
