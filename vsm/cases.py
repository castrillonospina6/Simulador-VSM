"""Fachada de casos: biblioteca (23 casos), generador aleatorio y enunciado.

Mantiene la API pública histórica: CASES, LEVELS, Case, get_case, generate_case, brief_html.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .case_model import (Case, ProcSpec, InvSpec, TransSpec, LEVELS, LEVEL_INFO, brief_html,
                         problems, special_counts, key_label)
from .cases_library import ALL_CASES
from .generator import generate_case

CASES: Dict[str, Case] = {c.id: c for c in ALL_CASES}
CASES_BY_LEVEL: Dict[str, List[Case]] = {lvl: [c for c in ALL_CASES if c.level == lvl] for lvl in LEVELS}

__all__ = ["Case", "ProcSpec", "InvSpec", "TransSpec", "CASES", "CASES_BY_LEVEL", "LEVELS", "LEVEL_INFO",
           "brief_html", "generate_case", "get_case", "problems", "special_counts", "key_label"]


def get_case(case_id: Optional[str]) -> Optional[Case]:
    """Recupera un caso por id (incluye los generados: 'gen-<nivel>-<semilla>')."""
    if not case_id:
        return None
    if case_id in CASES:
        return CASES[case_id]
    if case_id.startswith("gen-"):
        try:
            _, lvl, seed = case_id.split("-")
            return generate_case(int(seed), lvl.capitalize())
        except (ValueError, KeyError):
            return None
    return None
