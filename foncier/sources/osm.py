"""Routes et échangeurs autoroutiers depuis OpenStreetMap (API Overpass)."""
from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, Point

from .. import CRS_METRIQUE, CRS_WEB
from ..http import get_json

CLASSES = ("motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|"
           "motorway_link|trunk_link|primary_link|secondary_link|tertiary_link|service")


def _bbox(communes: gpd.GeoDataFrame, marge_m: float) -> str:
    minx, miny, maxx, maxy = communes.to_crs(CRS_METRIQUE).total_bounds
    b = gpd.GeoSeries.from_xy([minx - marge_m, maxx + marge_m], [miny - marge_m, maxy + marge_m],
                              crs=CRS_METRIQUE).to_crs(CRS_WEB)
    return f"{b.y.min()},{b.x.min()},{b.y.max()},{b.x.max()}"


def routes_et_echangeurs(cfg: dict, communes: gpd.GeoDataFrame):
    url = cfg["sources"]["overpass"]
    requete_routes = (f'[out:json][timeout:600];way["highway"~"^({CLASSES})$"]({_bbox(communes, 1000)});'
                      "out tags geom;")
    rep = get_json(url, method="POST", data={"data": requete_routes})
    lignes = []
    for el in rep.get("elements", []):
        geom = el.get("geometry") or []
        if len(geom) >= 2:
            lignes.append({"highway": el.get("tags", {}).get("highway"),
                           "ref": el.get("tags", {}).get("ref"),
                           "geometry": LineString([(p["lon"], p["lat"]) for p in geom])})
    routes = gpd.GeoDataFrame(lignes, geometry="geometry", crs=CRS_WEB).to_crs(CRS_METRIQUE)

    marge = cfg["agents"]["accessibilite"]["echangeur_max_m"]
    requete_ech = (f'[out:json][timeout:300];node["highway"="motorway_junction"]({_bbox(communes, marge)});'
                   "out;")
    rep = get_json(url, method="POST", data={"data": requete_ech})
    points = [{"nom": el.get("tags", {}).get("name"), "geometry": Point(el["lon"], el["lat"])}
              for el in rep.get("elements", []) if "lon" in el]
    echangeurs = gpd.GeoDataFrame(points, geometry="geometry", crs=CRS_WEB).to_crs(CRS_METRIQUE)
    if routes.empty:
        raise ValueError("Overpass n'a renvoyé aucune route")
    return routes, echangeurs
