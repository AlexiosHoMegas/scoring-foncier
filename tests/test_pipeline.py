import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from foncier import CRS_METRIQUE, agents, config, demo, filtres, run, score
from foncier.agents.outils import lineaire_decroissant, log_croissant, rang
from foncier.sources import insee

RACINE = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cfg():
    return config.charger(RACINE / "config.yaml")


@pytest.fixture(scope="module")
def donnees(cfg):
    return demo.generer(cfg)


# --- Outils de notation -------------------------------------------------------

def test_rang_bornes_et_inverse():
    s = pd.Series([10, 20, 30, np.nan])
    r = rang(s)
    assert r.iloc[0] == 0 and r.iloc[2] == 100 and np.isnan(r.iloc[3])
    assert rang(s, inverse=True).iloc[0] == 100


def test_lineaire_et_log():
    d = pd.Series([0, 2000, 8500, 15000, 30000])
    n = lineaire_decroissant(d, 2000, 15000)
    assert list(n.round()) == [100, 100, 50, 0, 0]
    t = log_croissant(pd.Series([100, 500, 40000, 1e6]), 500, 40000)
    assert list(t.round()) == [0, 0, 100, 100]


# --- Filtres ------------------------------------------------------------------

def _mini_donnees(cfg):
    d = demo.generer(cfg)
    parcelles = gpd.GeoDataFrame({
        "id": ["A", "B", "C", "D", "E"], "insee": "99001", "contenance": [5000, 1000, 5000, 5000, 5000],
    }, geometry=[box(0, 0, 100, 50), box(0, 60, 20, 110), box(200, 0, 300, 50),
                 box(0, 500, 100, 550), box(400, 0, 500, 50)], crs=CRS_METRIQUE)
    d.parcelles = parcelles
    d.zones = gpd.GeoDataFrame({"typezone": ["U", "A"], "libelle": ["UE", "A"], "formdomi": ["0201", None],
                                "urlfic": None}, geometry=[box(-10, -10, 150, 600), box(150, -10, 600, 600)],
                               crs=CRS_METRIQUE)
    d.routes = gpd.GeoDataFrame({"highway": ["residential", "residential"]},
                                geometry=[LineString([(-5, -20), (600, -20)]), LineString([(-5, 120), (150, 120)])],
                                crs=CRS_METRIQUE)
    d.batiments = gpd.GeoDataFrame({"insee": ["99001"]}, geometry=[box(400, 0, 480, 50)], crs=CRS_METRIQUE)
    d.prescriptions = d.prescriptions.iloc[0:0]
    d.ppr = d.ppr.iloc[0:0]
    return d


def test_filtres_motifs(cfg):
    p = filtres.appliquer(_mini_donnees(cfg), cfg).set_index("id")
    assert pd.isna(p.loc["A", "motif_exclusion"])                       # retenue
    assert p.loc["B", "motif_exclusion"] == "surface insuffisante"
    assert p.loc["C", "motif_exclusion"] == "zone non constructible"
    assert p.loc["D", "motif_exclusion"] == "enclavée"                  # à 380 m de la route
    assert p.loc["E", "motif_exclusion"] == "zone non constructible"    # zone A avant le bâti


def test_ebc_exclut(cfg):
    d = _mini_donnees(cfg)
    d.prescriptions = gpd.GeoDataFrame({"typepsc": ["01"], "libelle": ["EBC"]},
                                       geometry=[box(0, 0, 80, 50)], crs=CRS_METRIQUE)
    p = filtres.appliquer(d, cfg).set_index("id")
    assert p.loc["A", "motif_exclusion"] == "prescription bloquante"


# --- Agents et score ----------------------------------------------------------

def test_agents_notes_valides(cfg, donnees):
    tout = filtres.appliquer(donnees, cfg)
    cand = tout[tout["motif_exclusion"].isna()]
    notes = agents.executer(cand, donnees, cfg)
    for a in config.AGENTS:
        col = notes[f"note_{a}"]
        assert col.between(0, 100).all(), a
        assert col.notna().all(), a
    s = score.calculer(notes, cand, cfg)
    assert s.between(0, 100).all()


def test_prix_comparables_et_estimation(cfg):
    """Ventes en zone constructible seulement ; estimation = surface × médiane, fourchette Q1-Q3."""
    d = demo.generer(cfg)
    d.zones = gpd.GeoDataFrame({"typezone": ["U", "U", "A"], "libelle": None, "formdomi": None, "urlfic": None},
                               geometry=[box(-100, -100, 100, 100), box(9900, -100, 10100, 100),
                                         box(-100, 200, 100, 400)], crs=CRS_METRIQUE)
    prix = [20, 30, 40, 50, 60] + [200] * 5 + [1] * 5          # les ventes à 1 €/m² sont en zone A
    pts = ([Point(i * 10, 0) for i in range(5)] + [Point(10000 + i, 0) for i in range(5)]
           + [Point(i, 300) for i in range(5)])
    d.ventes = gpd.GeoDataFrame({"prix_m2": prix, "surface": 1000, "date": "2025-01-01",
                                 "id_mutation": range(15)}, geometry=pts, crs=CRS_METRIQUE)
    cand = gpd.GeoDataFrame({"surface_m2": [5000, 5000], "insee": "99001"},
                            geometry=[Point(0, 0).buffer(10), Point(10000, 0).buffer(10)], crs=CRS_METRIQUE)
    out = agents.prix.noter(cand, d, cfg["agents"]["prix"])
    assert out["prix_m2_median"].iloc[0] == 40           # les ventes agricoles sont ignorées
    assert out["prix_estime"].iloc[0] == 200000          # 5 000 m² x 40 €/m²
    assert out["prix_estime_bas"].iloc[0] == 150000 and out["prix_estime_haut"].iloc[0] == 250000
    assert out["note_prix"].iloc[0] > out["note_prix"].iloc[1]


def test_filtre_disponibilite(cfg):
    d = _mini_donnees(cfg)
    d.parcelles = pd.concat([d.parcelles, gpd.GeoDataFrame(
        {"id": ["F", "G", "H", "I"], "insee": "99001", "contenance": 5000},
        geometry=[box(0, 130, 100, 180), box(0, 200, 100, 250), box(0, 260, 100, 310), box(0, 320, 100, 370)],
        crs=CRS_METRIQUE)], ignore_index=True)
    d.routes = gpd.GeoDataFrame({"highway": ["residential"]}, geometry=[LineString([(-5, -20), (-5, 600)])],
                                crs=CRS_METRIQUE)
    d.proprietaires = pd.DataFrame({"id": ["F", "G"], "groupe": ["4", "0"], "forme": ["Commune", "SCI"],
                                    "denomination": ["COMMUNE X", "SCI Y"]})
    d.parcelles_vendues = pd.Series({"H": "2026-01-01"})
    d.parcelles_permis = {"I"}
    p = filtres.appliquer(d, cfg).set_index("id")
    assert p.loc["F", "motif_exclusion"] == "propriété publique"
    assert pd.isna(p.loc["G", "motif_exclusion"]) and p.loc["G", "proprietaire"] == "SCI Y"
    assert p.loc["H", "motif_exclusion"] == "vendue récemment"
    assert p.loc["I", "motif_exclusion"] == "projet en cours (permis)"
    assert p.loc["A", "proprietaire"] == "Particulier ou entreprise individuelle"


def test_devenue_constructible(cfg):
    d = _mini_donnees(cfg)
    d.zonage_precedent = {"AUs": ["A"], "A": ["C"]}
    p = filtres.appliquer(d, cfg).set_index("id")
    assert "devenue constructible" in p.loc["A", "drapeaux"]
    assert not p.loc["C", "nouveau_constructible"]     # toujours en zone A


def test_robustesse(cfg, donnees):
    tout = filtres.appliquer(donnees, cfg)
    cand = tout[tout["motif_exclusion"].isna()]
    notes = agents.executer(cand, donnees, cfg)
    r = score.robustesse(notes, cand, cfg)
    s = score.calculer(notes, cand, cfg)
    assert r.between(0, 100).all()
    assert r[s.nlargest(20).index].mean() > r[s.nsmallest(20).index].mean()


def test_lecture_proprietaires():
    from foncier.sources.proprietaires import lire_tableau
    brut = pd.DataFrame({
        "Département": ["34", "34", "12"], "Code Direction": ["0", "0", "0"],
        "Code Commune": ["172", "022", "001"], "Nom Commune": ["MONTPELLIER", "BAILLARGUES", "X"],
        "Préfixe": ["000", "", "000"], "Section": ["AB", "C", "A"], "N° plan": ["12", "345", "1"],
        "Groupe personne": ["4", "0", "0"], "Forme juridique": ["Commune", "Société civile immobilière", "SA"],
        "Forme juridique abrégée": ["COM", "SCI", "SA"], "Dénomination": ["COMMUNE DE MONTPELLIER", "SCI Z", "X"]})
    df = lire_tableau(brut, ["34"])
    assert list(df["id"]) == ["34172000AB0012", "340220000C0345"]
    assert list(df["groupe"]) == ["4", "0"] and df["denomination"].iloc[1] == "SCI Z"


def test_lecture_conso(tmp_path):
    from foncier.sources import conso
    f = tmp_path / "conso.csv"
    f.write_text("idcom;idcomtxt;naf11art21;naf21art25\n34172;Montpellier;1000000;400000\n01001;X;10;5\n",
                 encoding="utf-8")
    df = conso.lire(f, ["34172"])
    assert df.to_dict("records") == [{"insee": "34172", "m2_2011_2021": 1000000, "m2_2021_2025": 400000}]


def test_poids_changent_le_classement(cfg, donnees):
    tout = filtres.appliquer(donnees, cfg)
    cand = tout[tout["motif_exclusion"].isna()]
    notes = agents.executer(cand, donnees, cfg)
    seulement_surface = {**cfg, "poids": {a: (1 if a == "surface" else 0) for a in config.AGENTS}}
    s = score.calculer(notes, cand, seulement_surface)
    sans_drapeau = ~(cand["residentiel"] | cand["ppr"])
    assert np.allclose(s[sans_drapeau], notes.loc[sans_drapeau, "note_surface"].round(1))


# --- Bout en bout -------------------------------------------------------------

def test_execution_demo(cfg, tmp_path):
    meta = run.executer(cfg, tmp_path, mode_demo=True)
    assert meta["demo"] is True and meta["nb_candidates"] > 0
    c = json.loads((tmp_path / "parcelles.json").read_text(encoding="utf-8"))
    assert c["n"] == meta["nb_candidates"] == len(c["geometries"])
    for cle in ["id", "score", "surface_m2", *[f"note_{a}" for a in config.AGENTS]]:
        assert len(c["colonnes"][cle]) == c["n"]
    # Décodage identique à celui de la carte : premier point d'un anneau, puis écarts.
    anneau = c["geometries"][0][0][0]
    lon, lat = anneau[0] / c["echelle"], anneau[1] / c["echelle"]
    assert 2 < lon < 5 and 42 < lat < 45  # autour de Montpellier, en WGS84
    xs = np.cumsum(anneau[0::2]) / c["echelle"]
    assert xs.max() - xs.min() < 0.01  # une parcelle fait moins d'un kilomètre
    scores = c["colonnes"]["score"]
    assert scores == sorted(scores, reverse=True)


# --- Lecture INSEE ------------------------------------------------------------

def test_lecture_insee(tmp_path):
    lignes = [["Historique des populations"], [], ["CODGEO", "LIBGEO", "PMUN2023", "PMUN2013", "PSDC1999"],
              ["34172", "Montpellier", 300000, 270000, 225000], ["34022", "Baillargues", 7800, 6500, 5000]]
    chemin = tmp_path / "pop.xlsx"
    pd.DataFrame(lignes).to_excel(chemin, header=False, index=False)
    df = insee.lire(chemin, 10)
    assert list(df["insee"]) == ["34172", "34022"]
    assert df["ecart_annees"].iloc[0] == 10 and df["pop_recente"].iloc[0] == 300000


# --- Lecture des comptages routiers (colonnes vérifiées sur data.gouv.fr) -----

def test_lecture_trafic(tmp_path, monkeypatch, cfg):
    from foncier.sources import trafic
    comptages = tmp_path / "c.csv"
    comptages.write_text(
        "Identifiant du compteur;Année;mja_tv_tcj;mja_%pl_tcj;Latitude;Longitude\n"
        "Per.034.0001.00.3;2023;9000;5.1;43.6;3.9\n"
        "Per.034.0001.00.3;2024;9500;5.0;43.6;3.9\n"
        "Tou.034.0002.00.3;2024;3000;2.0;43.7;3.8\n", encoding="utf-8")
    sections = tmp_path / "s.csv"
    ligne = '{""type"": ""LineString"", ""coordinates"": [[3.90, 43.60], [3.91, 43.61]]}'
    sections.write_text(f'Identifiant du compteur;geo_shape\nPer.034.0001.00.3;"{ligne}"\n', encoding="utf-8")
    fichiers = {cfg["sources"]["trafic_comptages"]: comptages, cfg["sources"]["trafic_sections"]: sections}
    monkeypatch.setattr(trafic, "telecharger", lambda url, suffixe="": fichiers[url])
    g = trafic.sections(cfg)
    assert len(g) == 2
    ligne_mesuree = g[g["compteur"] == "Per.034.0001.00.3"].iloc[0]
    assert ligne_mesuree["tmja"] == 9500 and ligne_mesuree.geometry.geom_type == "LineString"
    assert g[g["compteur"] == "Tou.034.0002.00.3"].geometry.iloc[0].geom_type == "Point"


def test_identifiant_parcelle_sitadel():
    from foncier.sources.sitadel import _id_parcelle
    df = pd.DataFrame({"COMM": ["34172", "34022"], "SEC_CADASTRE1": ["AB", "C"], "NUM_CADASTRE1": ["12", "0345"]})
    assert list(_id_parcelle(df)) == ["34172000AB0012", "340220000C0345"]


def test_sitadel_lit_le_format_dido(tmp_path, monkeypatch, cfg, donnees):
    """Colonnes réelles du fichier DiDo (dictionnaire SDES) : NUM_DAU, SURF_LOC_CREEE, etc."""
    from foncier.sources import sitadel
    p0 = donnees.parcelles.iloc[0]
    entete = "REG_CODE;DEP_CODE;COMM;TYPE_DAU;NUM_DAU;DATE_REELLE_AUTORISATION;SEC_CADASTRE1;NUM_CADASTRE1;SURF_BUR_CREEE;SURF_LOC_CREEE"
    sec, num = p0["id"][8:10], p0["id"][10:]
    lignes = [entete,
              f"76;99;{p0['insee']};PC;X1;2025-03-01;{sec};{num};800;1200",
              f"76;99;{p0['insee']};PC;X2;2010-03-01;{sec};{num};0;5000",   # trop ancien
              "76;12;12001;PC;X3;2025-03-01;AB;1;0;900"]                       # autre département
    f = tmp_path / "locaux.csv"
    f.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    monkeypatch.setattr(sitadel, "_candidates", lambda cfg: ["fichier"])
    monkeypatch.setattr(sitadel, "entete", lambda url, n: f.read_bytes())
    monkeypatch.setattr(sitadel, "telecharger", lambda url, suffixe="": f)
    g = sitadel.permis_locaux(cfg, ["99"], donnees.parcelles, donnees.communes)
    assert list(g["surface_m2"]) == [1200]
    assert g.geometry.iloc[0].distance(p0.geometry.representative_point()) < 1
