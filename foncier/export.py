"""Écrit les fichiers lus par la carte : parcelles notées et métadonnées."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

from . import CRS_WEB
from .config import AGENTS

PROPRIETES = [
    "id", "insee", "commune", "surface_m2", "typezone", "libelle", "urlfic", "score", "classe",
    *[f"note_{a}" for a in AGENTS],
    "prix_m2_median", "prix_nb_ventes", "trafic_tmja", "trafic_source", "dist_echangeur_km",
    "dist_centre_km", "croissance_pop_an_pct", "locaux_autorises_m2", "drapeaux",
]


def ecrire(resultat: gpd.GeoDataFrame, parcelles_total: int, exclusions: pd.Series, d, cfg: dict,
           sortie: Path) -> dict:
    sortie.mkdir(parents=True, exist_ok=True)
    g = resultat.copy()
    g["geometry"] = g.geometry.simplify(0.5, preserve_topology=True)
    g = g.to_crs(CRS_WEB).sort_values("score", ascending=False)
    g["geometry"] = shapely.set_precision(g.geometry.values, 1e-6)
    colonnes = [k for k in PROPRIETES if k in g.columns]
    g = g[colonnes + ["geometry"]].copy()
    for c in g.columns.drop("geometry"):
        if g[c].dtype == bool or str(g[c].dtype) == "boolean":
            g[c] = g[c].astype(object)
    texte = g.to_json(na="null", drop_id=True, ensure_ascii=False)
    (sortie / "parcelles.geojson").write_text(texte, encoding="utf-8")

    meta = {
        "mise_a_jour": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "demo": d.demo,
        "territoire": cfg["territoire"]["nom"],
        "nb_communes": int(len(d.communes)),
        "nb_parcelles": int(parcelles_total),
        "nb_candidates": int(len(resultat)),
        "exclusions": {str(k): int(v) for k, v in exclusions.items()},
        "poids": cfg["poids"],
        "penalites": cfg.get("penalites", {}),
        "sources": d.sources,
        "emprise": list(map(float, g.total_bounds)) if len(g) else None,
    }
    (sortie / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta

