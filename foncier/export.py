"""Écrit les fichiers lus par la carte : parcelles notées et métadonnées.

Format compact `parcelles.json` (la carte le reconstruit en GeoJSON) :
- propriétés en colonnes, pour ne pas répéter les noms de champs à chaque parcelle ;
- coordonnées en entiers au millionième de degré, encodées en écarts successifs.
Sur les données réelles, le fichier est environ 4 fois plus léger que du GeoJSON.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import MultiPolygon, Polygon

from . import CRS_WEB
from .config import AGENTS

PROPRIETES = [
    "id", "commune", "surface_m2", "typezone", "libelle", "urlfic", "score",
    *[f"note_{a}" for a in AGENTS],
    "prix_m2_median", "prix_nb_ventes", "trafic_tmja", "trafic_source", "dist_echangeur_km",
    "dist_centre_km", "croissance_pop_an_pct", "locaux_autorises_m2", "budget_zan_consomme_pct",
    "prix_estime", "prix_estime_bas", "prix_estime_haut", "proprietaire", "forme_juridique",
    "robustesse", "mode", "prix_base", "note_ouverture", "dist_zone_urbaine_m",
    "urbanise_recent_ha", "drapeaux",
]


def ecrire(resultat: gpd.GeoDataFrame, parcelles_total: int, exclusions: pd.Series, d, cfg: dict,
           sortie: Path) -> dict:
    sortie.mkdir(parents=True, exist_ok=True)
    g = resultat.copy()
    g["geometry"] = g.geometry.simplify(0.5, preserve_topology=True)
    g = g.to_crs(CRS_WEB).sort_values("score", ascending=False)
    g["geometry"] = shapely.set_precision(g.geometry.values, 1e-6)
    colonnes = [k for k in PROPRIETES if k in g.columns]
    (sortie / "parcelles.json").write_text(
        json.dumps(compacter(g, colonnes), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ancien = sortie / "parcelles.geojson"
    if ancien.exists():
        ancien.unlink()

    meta = {
        "mise_a_jour": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "demo": d.demo,
        "territoire": cfg["territoire"]["nom"],
        "nb_communes": int(len(d.communes)),
        "nb_parcelles": int(parcelles_total),
        "nb_candidates": int(len(resultat)),
        "exclusions": {str(k): int(v) for k, v in exclusions.items()},
        "poids": cfg["poids"],
        "profils": {"general": {"nom": "Général", "poids": cfg["poids"]},
                    **{k: {"nom": v["nom"], "poids": v["poids"], "mode": v.get("mode", "constructible")}
                       for k, v in cfg.get("profils", {}).items()}},
        "plafond_publie": cfg.get("export", {}).get("prix_max_publie"),
        "nouvelles_constructibles": int(resultat.get("nouveau_constructible", pd.Series(dtype=bool)).sum()),
        "penalites": cfg.get("penalites", {}),
        "sources": d.sources,
        "emprise": list(map(float, g.total_bounds)) if len(g) else None,
    }
    (sortie / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta



def ecrire_zonage(tout: pd.DataFrame, cfg: dict, sortie: Path) -> None:
    """Liste des parcelles non constructibles, relue au prochain calcul pour repérer celles
    qui le deviennent."""
    autorisees = set(cfg["filtres"]["typezones_autorisees"])
    non = tout[tout["typezone"].notna() & ~tout["typezone"].isin(autorisees)]
    contenu = {
        "date": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "non_constructibles": {str(t): sorted(g["id"].astype(str)) for t, g in non.groupby("typezone")},
    }
    (sortie / "zonage.json").write_text(json.dumps(contenu, separators=(",", ":")), encoding="utf-8")


ECHELLE = 1_000_000  # millionième de degré, environ 10 cm


def _anneau(coords) -> list[int]:
    q = np.rint(np.asarray(coords)[:-1, :2] * ECHELLE).astype(np.int64)  # dernier point = premier
    d = np.vstack([q[:1], np.diff(q, axis=0)])
    return d.ravel().tolist()


def _geometrie(geom) -> list:
    polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms) if isinstance(geom, MultiPolygon) else []
    return [[_anneau(p.exterior.coords)] + [_anneau(i.coords) for i in p.interiors] for p in polys]


def _colonne(serie: pd.Series) -> list:
    valeurs = []
    for v in serie.tolist():
        if v is None or v is pd.NA or (isinstance(v, float) and np.isnan(v)):
            valeurs.append(None)
        elif isinstance(v, (float, np.floating)):
            valeurs.append(round(float(v), 1))
        elif isinstance(v, (np.integer,)):
            valeurs.append(int(v))
        elif isinstance(v, list):
            valeurs.append(v or None)
        else:
            valeurs.append(v)
    return valeurs


def compacter(g: gpd.GeoDataFrame, colonnes: list[str]) -> dict:
    return {
        "format": "parcelles-compact-1",
        "echelle": ECHELLE,
        "n": int(len(g)),
        "colonnes": {c: _colonne(g[c]) for c in colonnes},
        "geometries": [_geometrie(x) for x in g.geometry],
    }


def _fc(g: gpd.GeoDataFrame, colonnes: list[str], tolerance: float) -> dict:
    if g.empty:
        return {"type": "FeatureCollection", "features": []}
    g = g[colonnes + ["geometry"]].copy()
    g["geometry"] = g.geometry.simplify(tolerance, preserve_topology=True)
    g = g[~g.geometry.is_empty].to_crs(CRS_WEB)
    g["geometry"] = shapely.set_precision(g.geometry.values, 1e-5)
    return json.loads(g.to_json(na="null", drop_id=True))


def ecrire_couches(d, cfg: dict, sortie: Path) -> None:
    """Couches affichables sur la carte : aires de développement, grands axes, front d'urbanisation."""
    autorisees = set(cfg["filtres"]["typezones_autorisees"]) | set(cfg["filtres"].get("typezones_pari", []))
    zones_au = d.zones[d.zones["typezone"].isin(autorisees - {"U"})] if not d.zones.empty else d.zones
    axes = gpd.GeoDataFrame(columns=["classe", "tmja", "geometry"], geometry="geometry", crs=d.zones.crs)
    if not d.routes.empty:
        grands = d.routes[d.routes["highway"].isin(["motorway", "trunk", "primary"])].copy()
        grands["classe"] = grands["highway"]
        grands["tmja"] = None
        axes = grands[["classe", "tmja", "geometry"]]
    if not d.trafic.empty:
        mesures = d.trafic[d.trafic.geometry.geom_type.isin(["LineString", "MultiLineString"])].copy()
        mesures["classe"] = "comptage"
        axes = pd.concat([axes, mesures[["classe", "tmja", "geometry"]]], ignore_index=True)
    axes = gpd.GeoDataFrame(axes, geometry="geometry", crs=d.zones.crs)
    front = d.conso_grille.copy()
    if not front.empty:
        front["ha_recent"] = (front["m2_recent"] / 10000).round(1)
        front = front[front["ha_recent"] > 0]
    couches = {
        "zones_au": _fc(zones_au, ["typezone", "libelle"], 5),
        "axes": _fc(axes, ["classe", "tmja"], 15),
        "front": _fc(front, ["ha_recent"] if not front.empty else [], 1),
        "periode_front": d.conso_grille.attrs.get("periode_recente") if not d.conso_grille.empty else None,
    }
    (sortie / "couches.json").write_text(json.dumps(couches, ensure_ascii=False, separators=(",", ":")),
                                         encoding="utf-8")
