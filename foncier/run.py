"""Point d'entrée : python -m foncier.run [--demo] [--config config.yaml] [--sortie site/data]."""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import agents, config, demo, export, filtres, score

log = logging.getLogger("foncier")


def executer(cfg: dict, sortie: Path, mode_demo: bool = False) -> dict:
    t0 = time.time()
    if mode_demo:
        d = demo.generer(cfg)
    else:
        from . import sources
        d = sources.charger(cfg)

    tout = filtres.appliquer(d, cfg)
    exclusions = tout["motif_exclusion"].value_counts()
    candidats = tout[tout["motif_exclusion"].isna()].copy()
    noms = d.communes.set_index("insee")["nom"]
    candidats["commune"] = candidats["insee"].map(noms)

    notes = agents.executer(candidats, d, cfg)
    resultat = gpd.GeoDataFrame(candidats.join(notes), geometry="geometry", crs=candidats.crs)
    # Chaque mode est noté avec ses poids par défaut : « général » ou « pari long terme ».
    pari = candidats["mode"] == "pari"
    poids_pari = cfg.get("profils", {}).get("pari", {}).get("poids", cfg["poids"])
    resultat["score"] = score.calculer(notes, candidats, cfg)
    resultat["robustesse"] = score.robustesse(notes, candidats, cfg)
    if pari.any():
        resultat.loc[pari, "score"] = score.calculer(notes[pari], candidats[pari], cfg, poids_pari)
        resultat.loc[pari, "robustesse"] = score.robustesse(notes[pari], candidats[pari],
                                                            {**cfg, "poids": poids_pari})
        resultat.loc[~pari, "robustesse"] = score.robustesse(notes[~pari], candidats[~pari], cfg)
    resultat["classe"] = resultat["score"].map(score.classe)

    # Carte légère : on ne publie pas les terrains dont même l'estimation basse est hors de portée.
    plafond = cfg.get("export", {}).get("prix_max_publie")
    if plafond:
        trop_chers = resultat["prix_estime_bas"] > plafond
        log.info("Non publiées (estimation basse > %s €) : %d", plafond, int(trop_chers.sum()))
        resultat = resultat[~trop_chers]
        exclusions = pd.concat([exclusions, pd.Series({"prix hors plafond publié": int(trop_chers.sum())})])

    meta = export.ecrire(resultat, len(tout), exclusions, d, cfg, sortie)
    export.ecrire_zonage(tout, cfg, sortie)
    log.info("Terminé en %.0f s : %d parcelles notées sur %d", time.time() - t0,
             meta["nb_candidates"], meta["nb_parcelles"])
    return meta


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Scoring foncier automatique")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--sortie", default="site/data")
    p.add_argument("--demo", action="store_true", help="données fictives, sans réseau")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    executer(config.charger(a.config), Path(a.sortie), a.demo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
