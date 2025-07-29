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

def load_data(params):
    """Чете данните за оптимизация от базата.

    Очаква params dict с ключове:
      - 'selected_ids': списък от избраните ID на материали
      - 'constraints': [{'material_id': id, 'op': str, 'value': float}, ...]
        напр. {material_id: 3, op: '>=', value: 0.2}
      - 'prop_min', 'prop_max': граници за включване на колони

    Връща:
      - material_ids: list
      - property_values: np.ndarray(shape=(n, m))
      - target_profile: np.ndarray(length=m)
      - prop_columns: list
    """
    tbl = _get_materials_table(params.get('schema'))

    numeric_cols = [c.key for c in tbl.columns if _is_number(c.key)]
    numeric_cols.sort(key=lambda k: _parse_numeric(k))
    prop_cols = [c for c in numeric_cols
                 if params['prop_min'] <= _parse_numeric(c) <= params['prop_max']]

    stmt = select(tbl).where(tbl.c.id.in_(params['selected_ids']))
    rows = db.session.execute(stmt).mappings().all()

    if not rows:
        raise ValueError("Не са намерени материали за оптимизиране")
    if not prop_cols:
        raise ValueError("Няма подходящи числови колони в посочения диапазон")

    values = np.array([[row[c] for c in prop_cols] for row in rows], dtype=float)
    ids = [row['id'] for row in rows]

    if 'target_profile' in params and params['target_profile']:
        target = np.array(params['target_profile'], dtype=float)
    else:
        target = np.mean(values, axis=0)

    constraint_map = {}
    for c in params.get('constraints', []):
        mid = c.get('material_id')
        if mid in ids:
            idx = ids.index(mid)
            val = float(c.get('value', 0))
            op = c.get('op')
            lb, ub = constraint_map.get(idx, (0.0, 1.0))
            if op == '=':
                lb, ub = val, val
            elif op == '>=':
                lb = max(lb, val)
            elif op == '<=':
                ub = min(ub, val)
            constraint_map[idx] = (lb, ub)

    return ids, values, target, prop_cols, constraint_map

def compute_mse(weights, values, target):
    mixed = np.dot(weights, values)
    return float(np.mean((mixed - target) ** 2))


def optimize_continuous(values, target, constraints=None):
    """Continuous optimization using scipy's SLSQP solver.

    Parameters
    ----------
    values : np.ndarray
        Matrix with material properties.
    target : np.ndarray
        Desired property profile.
    constraints : dict, optional
        Index -> (lb, ub) bounds for the weight fractions.

    Returns
    -------
    tuple or None
        Returns ``(mse, weights)`` if successful, otherwise ``None``.
    """
    if minimize is None:
        raise RuntimeError("SciPy is required for continuous optimization")

    n = values.shape[0]
    x0 = np.full(n, 1.0 / n)
    bnds = [(0.0, 1.0) for _ in range(n)]
    if constraints:
        for idx, (lb, ub) in constraints.items():
            bnds[idx] = (lb, ub)

    def obj(w):
        return compute_mse(w, values, target)

    cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    res = minimize(obj, x0, bounds=bnds, constraints=cons, method="SLSQP")
    if res.success:
        return res.fun, res.x
    return None


def find_best_mix(
    values: np.ndarray,
    target: np.ndarray,
    max_components: int = MAX_COMPONENTS,
    mse_threshold: float | None = MSE_THRESHOLD,
    constraints: dict | None = None,
    progress_cb=None,
):
    """Enumerate material subsets and optimize each via SLSQP."""

    n = values.shape[0]
    combos = [
        combo
        for r in range(1, min(max_components, n) + 1)
        for combo in itertools.combinations(range(n), r)
    ]
    total = len(combos)
    best = None

    for idx, combo in enumerate(combos, 1):
        subvals = values[list(combo)]
        sub_constr = None
        if constraints:
            sub_constr = {
                pos: constraints[i]
                for pos, i in enumerate(combo)
                if i in constraints
            }
        out = optimize_continuous(subvals, target, sub_constr)
        if out:
            mse, weights = out
            if best is None or mse < best[0]:
                best = (mse, combo, weights)
        if progress_cb:
            best_mse = best[0] if best else None
            progress_cb(idx, total, best_mse)
        if best and mse_threshold is not None and best[0] <= mse_threshold:
            break

    return best
