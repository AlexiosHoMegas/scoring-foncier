"""Agent Surface : plus la parcelle est grande, plus la note est haute."""
from __future__ import annotations

import pandas as pd

from .outils import log_croissant


def noter(candidats, d, cfg) -> pd.DataFrame:
    out = pd.DataFrame(index=candidats.index)
    minimum = float(cfg.get("minimum_m2", 1000))
    out["note_surface"] = log_croissant(candidats["surface_m2"].astype(float), minimum,
                                        cfg["reference_m2"]).round(1)
    return out
