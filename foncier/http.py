"""Téléchargements avec cache disque et nouvelles tentatives."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "scoring-foncier/1.0 (pipeline open source)"


def cache_dir() -> Path:
    d = Path(os.environ.get("FONCIER_CACHE", ".cache"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cle(url: str, params: dict | None, data) -> str:
    corps = json.dumps(data, sort_keys=True) if isinstance(data, dict) else (data or "")
    brut = url + json.dumps(params or {}, sort_keys=True) + corps
    return hashlib.sha256(brut.encode()).hexdigest()[:32]


def _requete(method, url, *, params=None, data=None, stream=False, timeout=180, essais=4):
    attente = 5
    for essai in range(1, essais + 1):
        try:
            r = SESSION.request(method, url, params=params, data=data, stream=stream, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as e:
            statut = getattr(getattr(e, "response", None), "status_code", None)
            if statut is not None and statut < 500 and statut != 429:
                raise
            if essai == essais:
                raise
            log.warning("Échec %s (%s), nouvel essai dans %ss", url, e, attente)
            time.sleep(attente)
            attente *= 2


def get_json(url: str, params: dict | None = None, *, method: str = "GET", data: dict | str | None = None,
             cache: bool = True):
    chemin = cache_dir() / f"{_cle(url, params, data)}.json"
    if cache and chemin.exists():
        return json.loads(chemin.read_text(encoding="utf-8"))
    r = _requete(method, url, params=params, data=data)
    contenu = r.json()
    chemin.write_text(json.dumps(contenu), encoding="utf-8")
    return contenu


def get_texte(url: str, params: dict | None = None) -> str:
    return _requete("GET", url, params=params).text


def telecharger(url: str, suffixe: str = "", cache: bool = True) -> Path:
    """Télécharge un fichier en flux vers le cache et renvoie son chemin."""
    chemin = cache_dir() / f"{_cle(url, None, None)}{suffixe}"
    if cache and chemin.exists() and chemin.stat().st_size > 0:
        return chemin
    tmp = chemin.with_suffix(chemin.suffix + ".part")
    r = _requete("GET", url, stream=True, timeout=600)
    with open(tmp, "wb") as f:
        for bloc in r.iter_content(chunk_size=1 << 20):
            f.write(bloc)
    tmp.replace(chemin)
    return chemin


def entete(url: str, octets: int = 65536) -> bytes:
    """Lit seulement le début d'un fichier distant (pour identifier ses colonnes)."""
    r = _requete("GET", url, stream=True, timeout=120)
    lu = b""
    for bloc in r.iter_content(chunk_size=8192):
        lu += bloc
        if len(lu) >= octets:
            break
    r.close()
    return lu
