"""Chargement des données réelles depuis les sources ouvertes."""
from __future__ import annotations

import logging
import traceback

import geopandas as gpd
from shapely.geometry import Point

from .. import CRS_METRIQUE, CRS_WEB
from ..donnees import Donnees, gdf_vide
from . import cadastre, dvf, insee, osm, plu, sitadel, territoire, trafic

log = logging.getLogger(__name__)


def _essayer(nom: str, etats: dict, fonction, *args, defaut=None, obligatoire=False):
    try:
        resultat = fonction(*args)
        taille = len(resultat) if hasattr(resultat, "__len__") else None
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
    ventes = _essayer("dvf", etats, dvf.ventes_terrains, cfg, deps)
    import pandas as pd
    population = _essayer("insee_population", etats, insee.population, cfg, defaut=pd.DataFrame())
    permis = _essayer("sitadel", etats, sitadel.permis_locaux, cfg, deps, parcelles, communes)

    c = cfg["territoire"]["centre"]
    centre = gpd.GeoDataFrame(geometry=[Point(c["lon"], c["lat"])], crs=CRS_WEB).to_crs(CRS_METRIQUE)
    return Donnees(communes=communes, parcelles=parcelles, zones=zones, batiments=batiments,
                   prescriptions=prescriptions, ppr=ppr, routes=routes, echangeurs=echangeurs,
                   trafic=trafic_, ventes=ventes, population=population, permis=permis,
                   centre=centre, sources=etats, demo=False)
