"""Progresión del estudiante: cinturones, XP, racha y caso del día. Sin PyQt5.

Reglas
------
* Cada caso da XP según su nivel (LEVEL_XP). XP del intento = base × puntaje neto / 100, más un 25 % extra
  si el puntaje neto es ≥ 90. Solo suma XP si el puntaje neto es ≥ 75 (aprobado).
* Puntaje neto = puntaje de la evaluación − costo de las pistas usadas (ver hints.py).
* Solo se gana la DIFERENCIA sobre tu mejor marca en ese caso: repetir un caso no permite «cultivar» XP.
* Los casos aleatorios (id «gen-…») dan la mitad de XP, porque hay infinitos.
* Caso del día: uno de la biblioteca, igual para todos los usuarios ese día. Al aprobarlo por primera vez
  ese día: +50 % del XP del caso y un bono de racha (5 XP por día consecutivo, tope 7 días).
* Si el estudiante vio la solución de referencia de un caso, el intento no suma XP (lo decide la ventana).
* El progreso se guarda en JSON (por defecto ~/.simulador_vsm/progreso.json; variable de entorno
  VSM_PROGRESS_FILE para cambiarlo).
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from .case_model import Case, LEVELS
from .cases_library import ALL_CASES
from .evaluation import EvaluationResult, PASS_SCORE, _rating


# ---------------------------------------------------------------- cinturones
@dataclass(frozen=True)
class Belt:
    name: str
    min_xp: int
    color: str


BELTS: Tuple[Belt, ...] = (
    Belt("Junior", 0, "#95a5a6"),
    Belt("Blanco", 60, "#ecf0f1"),
    Belt("Amarillo", 200, "#f1c40f"),
    Belt("Verde", 450, "#27ae60"),
    Belt("Rojo", 800, "#c0392b"),
    Belt("Negro", 1200, "#17202a"),
)

LEVEL_XP = {"Junior": 20, "Blanco": 30, "Amarillo": 45, "Verde": 60, "Rojo": 80, "Negro": 100}
EXCELLENT_SCORE = 90.0
EXCELLENT_BONUS = 0.25
GENERATED_FACTOR = 0.5
DAILY_BONUS = 0.5
STREAK_XP_PER_DAY = 5
STREAK_CAP_DAYS = 7


def belt_for(xp: int) -> Belt:
    cur = BELTS[0]
    for b in BELTS:
        if xp >= b.min_xp:
            cur = b
    return cur


def next_belt(xp: int) -> Optional[Belt]:
    return next((b for b in BELTS if b.min_xp > xp), None)


# ---------------------------------------------------------------- XP por caso
def is_generated(case: Case) -> bool:
    return case.id.startswith("gen-")


def case_base_xp(case: Case) -> float:
    return LEVEL_XP.get(case.level, 0) * (GENERATED_FACTOR if is_generated(case) else 1.0)


def xp_for_score(case: Case, net_score: float) -> int:
    """XP que vale un puntaje neto en este caso (0 si no aprueba)."""
    if net_score < PASS_SCORE:
        return 0
    base = case_base_xp(case)
    xp = round(base * net_score / 100.0)
    if net_score >= EXCELLENT_SCORE:
        xp += round(base * EXCELLENT_BONUS)
    return int(xp)


def max_case_xp(case: Case) -> int:
    return xp_for_score(case, 100.0)


# ---------------------------------------------------------------- caso del día
def daily_case(day: Optional[date] = None) -> Case:
    """Caso del día: recorre la biblioteca sin repetir en 23 días (7 y 23 son coprimos)."""
    day = day or date.today()
    return ALL_CASES[(day.toordinal() * 7) % len(ALL_CASES)]


# ---------------------------------------------------------------- resultado de un intento
@dataclass
class AttemptResult:
    raw: float
    penalty: float
    net: float
    passed: bool
    counted: bool
    belt_before: Belt
    belt_after: Belt
    base_xp: int = 0
    daily_bonus: int = 0
    streak: int = 0
    streak_bonus: int = 0
    is_daily: bool = False

    @property
    def total(self) -> int:
        return self.base_xp + self.daily_bonus + self.streak_bonus

    @property
    def promoted(self) -> bool:
        return self.belt_after.name != self.belt_before.name


def adjust_result(res: EvaluationResult, net: float) -> EvaluationResult:
    """Copia de la evaluación con el puntaje neto (tras descontar pistas)."""
    return replace(res, score=net, rating=_rating(net), passed=net >= PASS_SCORE)


def default_path() -> str:
    return os.environ.get("VSM_PROGRESS_FILE") or os.path.join(os.path.expanduser("~"), ".simulador_vsm",
                                                              "progreso.json")


# ---------------------------------------------------------------- almacén
class Progress:
    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.xp = 0
        self.cases: Dict[str, dict] = {}
        self.daily: Dict[str, object] = {"last_done": "", "streak": 0, "best_streak": 0}
        if path:
            self.load()

    @classmethod
    def default(cls) -> "Progress":
        return cls(default_path())

    # -- persistencia
    def to_dict(self) -> dict:
        return {"version": 1, "xp": self.xp, "cases": self.cases, "daily": self.daily}

    def load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            xp = int(d.get("xp", 0))
            cases = {str(k): dict(v) for k, v in d.get("cases", {}).items()}
            daily = dict(d.get("daily", {}))
        except (OSError, ValueError, TypeError, AttributeError):
            try:                                   # archivo dañado: se conserva una copia y se empieza de cero
                os.replace(self.path, self.path + ".bak")
            except OSError:
                pass
            return
        self.xp = max(0, xp)
        self.cases = cases
        self.daily.update({"last_done": str(daily.get("last_done", "")),
                           "streak": int(daily.get("streak", 0) or 0),
                           "best_streak": int(daily.get("best_streak", 0) or 0)})

    def save(self) -> None:
        if not self.path:
            return
        try:
            folder = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(folder, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass          # el progreso es un extra: un disco de solo lectura no debe romper la evaluación

    def reset(self) -> None:
        self.xp = 0
        self.cases = {}
        self.daily = {"last_done": "", "streak": 0, "best_streak": 0}
        self.save()

    # -- consultas
    @property
    def belt(self) -> Belt:
        return belt_for(self.xp)

    def entry(self, case_id: str) -> dict:
        e = self.cases.get(case_id, {})
        return {"level": e.get("level", ""), "attempts": int(e.get("attempts", 0)),
                "best_net": float(e.get("best_net", 0.0)), "xp": int(e.get("xp", 0)),
                "passed": bool(e.get("passed", False))}

    def daily_done(self, today: Optional[date] = None) -> bool:
        return self.daily["last_done"] == (today or date.today()).isoformat()

    def current_streak(self, today: Optional[date] = None) -> int:
        """Racha vigente: sigue viva si el último caso del día fue hoy o ayer."""
        today = today or date.today()
        last = self.daily["last_done"]
        if last in (today.isoformat(), (today - timedelta(days=1)).isoformat()):
            return int(self.daily["streak"])
        return 0

    def level_summary(self) -> List[Tuple[str, int, int, int, int]]:
        """(nivel, superados, total, XP ganada, XP máxima) solo con casos de la biblioteca."""
        out = []
        for lvl in LEVELS:
            cs = [c for c in ALL_CASES if c.level == lvl]
            done = sum(1 for c in cs if self.entry(c.id)["passed"])
            out.append((lvl, done, len(cs), sum(self.entry(c.id)["xp"] for c in cs),
                        sum(max_case_xp(c) for c in cs)))
        return out

    # -- registrar un intento
    def record(self, case: Case, raw_score: float, penalty: float = 0.0, today: Optional[date] = None,
               count: bool = True) -> AttemptResult:
        today = today or date.today()
        net = max(0.0, round(raw_score - penalty, 1))
        before = self.belt
        att = AttemptResult(raw_score, penalty, net, net >= PASS_SCORE, count, before, before)
        if not count:
            return att

        e = self.entry(case.id)
        e["level"] = case.level
        e["attempts"] += 1
        e["best_net"] = max(e["best_net"], net)
        earned = xp_for_score(case, net)
        att.base_xp = max(0, earned - e["xp"])
        e["xp"] = max(e["xp"], earned)
        e["passed"] = e["passed"] or att.passed
        self.cases[case.id] = e

        if att.passed and case.id == daily_case(today).id and not self.daily_done(today):
            last = self.daily["last_done"]
            yesterday = (today - timedelta(days=1)).isoformat()
            streak = int(self.daily["streak"]) + 1 if last == yesterday else 1
            self.daily.update({"last_done": today.isoformat(), "streak": streak,
                               "best_streak": max(int(self.daily["best_streak"]), streak)})
            att.is_daily = True
            att.streak = streak
            att.daily_bonus = round(earned * DAILY_BONUS)
            att.streak_bonus = min(streak, STREAK_CAP_DAYS) * STREAK_XP_PER_DAY

        self.xp += att.total
        att.belt_after = self.belt
        self.save()
        return att


# ---------------------------------------------------------------- texto del resultado
def attempt_html(att: AttemptResult) -> str:
    out = ["<h3>Progreso</h3>"]
    line = f"Puntaje de la evaluación <b>{att.raw:g}</b>"
    if att.penalty:
        line += f" − pistas <b>{att.penalty:g}</b> = <b>{att.net:g}</b>"
    out.append(f"<p>{line}.</p>")
    if not att.counted:
        out.append("<p><i>Viste la solución de referencia de este caso: este intento no suma XP.</i></p>")
    elif not att.passed:
        out.append(f"<p>Necesitas <b>{PASS_SCORE:g}</b> puntos netos para ganar XP con este caso.</p>")
    elif att.total:
        parts = []
        if att.base_xp:
            parts.append(f"{att.base_xp} por el caso")
        if att.daily_bonus:
            parts.append(f"{att.daily_bonus} de bono del caso del día")
        if att.streak_bonus:
            parts.append(f"{att.streak_bonus} por tu racha de {att.streak} día(s)")
        out.append(f"<p><b>+{att.total} XP</b> ({', '.join(parts)}).</p>")
    else:
        out.append("<p>Sin XP nuevo: ya tenías esta marca o una mejor en este caso. "
                   "Mejora tu puntaje (menos pistas, más exactitud) para ganar la diferencia.</p>")
    if att.is_daily:
        out.append("<p>⭐ <b>Caso del día completado.</b></p>")
    if att.promoted:
        out.append(f"<p style='color:#1e8449'>🎉 <b>¡Subiste al Cinturón {att.belt_after.name}!</b></p>")
    return "\n".join(out)
