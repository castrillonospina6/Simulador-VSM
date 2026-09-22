"""Guardar / cargar el mapa completo como JSON (.vsm.json)."""
from __future__ import annotations

import json

from .models import VSMMap

EXTENSION = ".vsm.json"


def save_map(vmap: VSMMap, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(vmap.to_dict(), f, ensure_ascii=False, indent=2)


def load_map(path: str) -> VSMMap:
    with open(path, "r", encoding="utf-8") as f:
        return VSMMap.from_dict(json.load(f))
