"""Filtres éliminatoires, appliqués du moins coûteux au plus coûteux.

Chaque parcelle exclue garde le motif de sa première exclusion.
"""
from __future__ import annotations

import logging

import geopandas as gpd
import pandas as pd

from .donnees import Donnees

log = logging.getLogger(__name__)


def _ratio_recouvrement(parcelles: gpd.GeoDataFrame, couche: gpd.GeoDataFrame) -> pd.Series:
    """Part de la surface de chaque parcelle couverte par la couche (0 à 1)."""
    ratio = pd.Series(0.0, index=parcelles.index)
    if couche.empty or parcelles.empty:
        return ratio
    p = parcelles[["geometry"]].reset_index(names="_idx")
    inter = gpd.overlay(p, couche[["geometry"]], how="intersection", keep_geom_type=True)
    if inter.empty:
        return ratio
    couvert = inter.assign(_a=inter.geometry.area).groupby("_idx")["_a"].sum()
    ratio.loc[couvert.index] = (couvert / parcelles.loc[couvert.index].geometry.area).clip(0, 1)
    return ratio


def appliquer(d: Donnees, cfg: dict) -> gpd.GeoDataFrame:
    f = cfg["filtres"]
    p = d.parcelles.copy()
    p["motif_exclusion"] = pd.NA
    p["surface_m2"] = p["contenance"].astype(float)
    p["drapeaux"] = [[] for _ in range(len(p))]

    def exclure(masque: pd.Series, motif: str):
        cible = masque & p["motif_exclusion"].isna()
        p.loc[cible, "motif_exclusion"] = motif
        log.info("Filtre %-28s : %6d parcelles exclues", motif, int(cible.sum()))

    def actives() -> pd.Series:
        return p["motif_exclusion"].isna()

    # 1. Surface (le plus rapide).
    exclure(p["surface_m2"] < f["surface_min_m2"], "surface insuffisante")

    # 2. Zonage d'urbanisme, au point intérieur de la parcelle.
    pts = gpd.GeoDataFrame(geometry=p.loc[actives()].geometry.representative_point(), crs=p.crs)
    jointure = gpd.sjoin(pts, d.zones[["typezone", "libelle", "formdomi", "urlfic", "geometry"]],
                         how="left", predicate="within")
    jointure = jointure[~jointure.index.duplicated(keep="first")]
    for c in ("typezone", "libelle", "formdomi", "urlfic"):
        p[c] = jointure[c].reindex(p.index)
    exclure(actives() & p["typezone"].isna(), "hors document d'urbanisme")
    exclure(actives() & ~p["typezone"].isin(f["typezones_autorisees"]), "zone non constructible")

    # 3. Vocation : zones d'habitat signalées.
    residentiel = p["formdomi"].fillna("").astype(str).str.startswith("01")
    if f.get("exclure_residentiel"):
        exclure(actives() & residentiel, "zone résidentielle")

    # 4. Accès à une voie carrossable.
    if not d.routes.empty:
        roulables = d.routes[d.routes["highway"] != "motorway"]
        a = p.loc[actives(), ["geometry"]]
        proche = gpd.sjoin_nearest(a, roulables[["geometry"]], how="left",
                                   max_distance=f["acces_route_max_m"], distance_col="_d")
        proche = proche[~proche.index.duplicated(keep="first")]
        exclure(actives() & proche["_d"].reindex(p.index).isna() & p.index.isin(a.index), "enclavée")
    else:
        log.warning("Pas de données routières : filtre d'accès ignoré")

    # 5. Prescriptions bloquantes (espace boisé classé, emplacement réservé).
    if not d.prescriptions.empty:
        bloquantes = d.prescriptions[d.prescriptions["typepsc"].isin(f["prescriptions_exclues"])]
        ratio = _ratio_recouvrement(p.loc[actives()], bloquantes)
        exclure(ratio.reindex(p.index).fillna(0) > f["recouvrement_prescription_max"],
                "prescription bloquante")

    # 6. Parcelle libre : peu de bâti.
    emprise = _ratio_recouvrement(p.loc[actives()], d.batiments)
    p["emprise_batie"] = emprise.reindex(p.index)
    exclure(p["emprise_batie"].fillna(0) > f["emprise_batie_max"], "déjà bâtie")

    # 7. Disponibilité probable.
    dispo = cfg.get("disponibilite", {})
    if not d.proprietaires.empty:
        proprio = d.proprietaires.set_index("id")
        p["proprietaire"] = p["id"].map(proprio["denomination"])
        p["forme_juridique"] = p["id"].map(proprio["forme"])
        groupe = p["id"].map(proprio["groupe"])
        exclure(groupe.isin([str(g) for g in dispo.get("groupes_proprietaires_exclus", [])]),
                "propriété publique")
        # Absente du fichier des personnes morales : particulier ou entreprise individuelle.
        p.loc[groupe.isna(), "proprietaire"] = "Particulier ou entreprise individuelle"
    if len(d.parcelles_vendues):
        p["vendue_le"] = p["id"].map(d.parcelles_vendues)
        exclure(p["vendue_le"].notna(), "vendue récemment")
    if d.parcelles_permis:
        exclure(p["id"].isin(d.parcelles_permis), "projet en cours (permis)")

    # 8. Risques naturels : périmètre de PPR.
    ppr = pd.Series(False, index=p.index)
    if not d.ppr.empty:
        a = p.loc[actives(), ["geometry"]]
        touche = gpd.sjoin(a, d.ppr[["geometry"]], how="inner", predicate="intersects").index.unique()
        ppr.loc[touche] = True
    if f.get("exclure_ppr"):
        exclure(actives() & ppr, "périmètre PPR")

    p["residentiel"] = residentiel & actives()
    p["ppr"] = ppr & actives()
    for i in p.index[p["residentiel"]]:
        p.at[i, "drapeaux"].append("zone résidentielle")
    for i in p.index[p["ppr"]]:
        p.at[i, "drapeaux"].append("périmètre PPR")

    # Parcelles devenues constructibles depuis la publication précédente.
    anciens = {i for ids in d.zonage_precedent.values() for i in ids}
    p["nouveau_constructible"] = p["id"].isin(anciens) & p["typezone"].isin(f["typezones_autorisees"])
    for i in p.index[p["nouveau_constructible"] & actives()]:
        p.at[i, "drapeaux"].append("devenue constructible")
    log.info("Parcelles devenues constructibles : %d", int(p["nouveau_constructible"].sum()))
    log.info("Candidates retenues : %d / %d", int(actives().sum()), len(p))
    return p
