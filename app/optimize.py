
"""Core optimization helpers."""

import numpy as np

from sqlalchemy import MetaData, Table, select
from flask import session, has_request_context
from flask_login import current_user
from typing import Optional
import itertools
import re

try:  # SciPy is optional during development
    from scipy.optimize import minimize
except Exception:  # pragma: no cover
    minimize = None

from . import db

# ── Constants ────────────────────────────────────────────────────────────────
MAX_COMPONENTS = 7        # максимален брой материали в сместа
MSE_THRESHOLD  = 0.0004
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

def find_best_mix(values: np.ndarray, target: np.ndarray):
    """Enumerate material subsets and optimize each via SLSQP."""

    n = values.shape[0]
    combos = [
        combo
        for r in range(1, min(MAX_COMPONENTS, n) + 1)
        for combo in itertools.combinations(range(n), r)
    ]
    best = None

    for combo in combos:
        subvals = values[list(combo)]
        out = optimize_continuous(subvals, target)
        if out:
            mse, weights = out
            if best is None or mse < best[0]:
                best = (mse, combo, weights)
        if best and best[0] <= MSE_THRESHOLD:
            break

    return best


def run_full_optimization(schema: Optional[str] = None):
    """Helper that loads data and returns the best mix."""

    ids, values, target, prop_cols = load_data(schema)
    result = find_best_mix(values, target)
    if not result:
        return None
    mse, combo, weights = result
    return {
        'material_ids': [ids[i] for i in combo],
        'weights':      weights.tolist(),
        'best_mse':     mse,
        'prop_columns': prop_cols,
        'target_profile': target.tolist(),
    }
