
"""Core optimization helpers."""

import numpy as np

from sqlalchemy import MetaData, Table, select
from flask import session, has_request_context
from flask_login import current_user
from typing import Optional
import re

try:  # SciPy is optional during development
    from scipy.optimize import minimize
except Exception:  # pragma: no cover
    minimize = None

from . import db

# ── Constants ─────────────────────────────────────────────────────────
# Степента за нормализация на профилите
# Изведена от предоставените Excel формули

POWER = 0.2175
# ─────────────────────────────────────────────────────────────────────────────

import re

NUM_RE = re.compile(r'^\d+(?:\.\d+)?')


def _parse_numeric(val: str):
    """Return numeric prefix of the column name or None."""
    if val is None:
        return None
    m = NUM_RE.match(str(val))
    if m:
        try:
            return float(m.group(0))
        except ValueError:
            return None
    return None


def _is_number(val: str) -> bool:
    return _parse_numeric(val) is not None

def _get_materials_table(schema: Optional[str] = None):
    """Връща таблицата materials_grit за указаната или текущата схема.

    If ``schema`` е None и няма active request context, връща ``main``.
    """
    if schema:
        sch = schema
    elif has_request_context() and getattr(current_user, "role", None) == "operator":
        sch = session.get("schema", "main")
    else:
        sch = "main"
    meta = MetaData(schema=sch)
    return Table("materials_grit", meta, autoload_with=db.engine)

def load_data(schema: Optional[str] = None):
    """Взима всички материали и числови колони от базата."""

    tbl = _get_materials_table(schema)

    numeric_cols = [c.key for c in tbl.columns if _is_number(c.key)]
    numeric_cols.sort(key=lambda k: _parse_numeric(k))

    stmt = select(tbl)
    if 'user_id' in tbl.c:
        stmt = stmt.where(tbl.c.user_id == current_user.id)

    rows = db.session.execute(stmt).mappings().all()

    if not rows:
        raise ValueError("Не са намерени материали за оптимизиране")
    if not numeric_cols:
        raise ValueError("Няма подходящи числови колони")

    values = np.array([[row[c] for c in numeric_cols] for row in rows], dtype=float)
    ids = [row['id'] for row in rows]

    target = np.mean(values, axis=0)

    return ids, values, target, numeric_cols

def compute_mse(weights, values, target):
    mixed = np.dot(weights, values)
    return float(np.mean((mixed - target) ** 2))


def normalize_row(row: np.ndarray, power: float = POWER) -> np.ndarray:
    """Normalize a numeric row using the specified exponent."""
    row = np.asarray(row, dtype=float)
    mn = row.min()
    mx = row.max()
    if mx == mn:
        return np.zeros_like(row)
    return (row ** power - mn ** power) / (mx ** power - mn ** power)


def etalon_from_columns(columns: list[str], power: float = POWER) -> np.ndarray:
    """Return normalized profile computed only from column names."""
    nums = np.array([_parse_numeric(c) for c in columns], dtype=float)
    return normalize_row(nums, power)



def optimize_continuous(values, target):
    """Continuous optimization using scipy's SLSQP solver."""

    if minimize is None:
        raise RuntimeError("SciPy is required for continuous optimization")

    n = values.shape[0]
    x0 = np.full(n, 1.0 / n)
    bnds = [(0.0, 1.0) for _ in range(n)]

    def obj(w):
        return compute_mse(w, values, target)

    cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    res = minimize(obj, x0, bounds=bnds, constraints=cons, method="SLSQP")
    if res.success:
        return res.fun, res.x
    return None

def run_full_optimization(schema: Optional[str] = None):
    """Helper that loads data and returns the best mix."""

    ids, values, _target, prop_cols = load_data(schema)

    etalon = etalon_from_columns(prop_cols)

    result = optimize_continuous(values, etalon)
    if not result:
        return None
    mse, weights = result
    mixed = np.dot(weights, values)
    return {
        'material_ids': ids,
        'weights':      weights.tolist(),
        'best_mse':     mse,
        'prop_columns': prop_cols,
        'target_profile': etalon.tolist(),
        'mixed_profile':  mixed.tolist(),
    }
