import numpy as np
from sqlalchemy import MetaData, Table, inspect, select
from flask import session, has_request_context
from typing import Optional
from flask_login import current_user
import itertools
try:
    from scipy.optimize import minimize
except Exception:  # pragma: no cover - optional dependency
    minimize = None

from . import db

# ==== Параметри ==== #
MAX_COMPONENTS  = 3        # максимален брой материали в сместа
MSE_THRESHOLD   = 0.0004
WEIGHT_STEP     = 0.1      # стъпка при изчерпателното претърсване на дяловете
# ==================== #

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

def optimize_combo(
    values,
    target,
    mse_threshold: float = MSE_THRESHOLD,
    max_components: int = MAX_COMPONENTS,
    weight_step: float = WEIGHT_STEP,
    progress_cb=None,
    constraints=None,
    cancel_cb=None,
):
    """Exhaustively search all material subsets and weight fractions.

    For every subset of materials up to ``max_components`` elements, all
    weight vectors with granularity ``weight_step`` that sum to 1 are
    evaluated. The best combination is returned, stopping early if its
    MSE drops below ``mse_threshold``.
    Parameters
    ----------
    values : np.ndarray
        Matrix with material properties.
    target : np.ndarray
        Desired property profile.
    mse_threshold : float
        Stop early if a combination reaches this MSE.
    max_components : int
        Maximum number of materials allowed in a mixture.
    weight_step : float
        Resolution of the weight search grid.
    progress_cb : callable
        Called as ``progress_cb(iteration, best_mse)`` after each step.
    constraints : dict
        Ключ: индекс на материала, стойност: (min, max) ограничения на дяловете.
    cancel_cb : callable, optional
        If provided, ``cancel_cb()`` is checked each iteration and stops the
        search when it returns ``True``.
    """
    n = values.shape[0]
    best_mse = float("inf")
    best_w = None
    step = 0

    # number of discrete steps (e.g. 0.1 -> 10)
    n_steps = int(round(1.0 / weight_step))

    def _subset_valid(sub):
        if not constraints:
            return True
        for idx, (lb, _ub) in constraints.items():
            if idx not in sub and lb > 0:
                return False
        return True

    def _weights_valid(sub, w_sub):
        if not constraints:
            return True
        for pos, idx in enumerate(sub):
            lb, ub = constraints.get(idx, (0.0, 1.0))
            if w_sub[pos] < lb - 1e-9 or w_sub[pos] > ub + 1e-9:
                return False
        return True

    weight_cache = {}

    def _weight_vectors(k):
        if k in weight_cache:
            return weight_cache[k]
        vecs = []

        def rec(prefix, remaining, idx):
            if idx == k - 1:
                prefix.append(remaining)
                vecs.append(np.array(prefix, dtype=float) * weight_step)
                prefix.pop()
                return
            for i in range(remaining + 1):
                prefix.append(i)
                rec(prefix, remaining - i, idx + 1)
                prefix.pop()

        rec([], n_steps, 0)
        weight_cache[k] = vecs
        return vecs

    max_components = min(max_components, n)

    for k in range(1, max_components + 1):
        vecs = _weight_vectors(k)
        for combo in itertools.combinations(range(n), k):
            if not _subset_valid(combo):
                continue
            for w_sub in vecs:
                if cancel_cb and cancel_cb():
                    return None
                step += 1
                if not _weights_valid(combo, w_sub):
                    if progress_cb:
                        progress_cb(step, best_mse)
                    continue
                w = np.zeros(n)
                for pos, idx in enumerate(combo):
                    w[idx] = w_sub[pos]
                mse = compute_mse(w, values, target)
                if mse < best_mse:
                    best_mse, best_w = mse, w
                if progress_cb:
                    progress_cb(step, best_mse)
                if best_mse <= mse_threshold:
                    return best_mse, best_w


    if best_w is not None:
        return best_mse, best_w
    return None


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
