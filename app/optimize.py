import numpy as np
from sqlalchemy import MetaData, Table, inspect, select
from flask import session, has_request_context
from typing import Optional
from flask_login import current_user

from . import db

# ==== Параметри ==== #
MAX_COMBINATIONS = 7
MSE_THRESHOLD = 0.0004
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
      - target_profile: np.ndarray(length=m)  # средни стойности на избраните материали
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
    target = np.mean(values, axis=0)
    ids = [row['id'] for row in rows]

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
    max_iter: int = MAX_COMBINATIONS,
    mse_threshold: float = MSE_THRESHOLD,
    progress_cb=None,
    constraints=None,
    cancel_cb=None,
):
    """Simple random search optimization.

    Parameters
    ----------
    values : np.ndarray
        Matrix with material properties.
    target : np.ndarray
        Desired property profile.
    max_iter : int
        How many random weight sets to try.
    mse_threshold : float
        Stop early if a combination reaches this MSE.
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
    def _satisfies(w):
        if not constraints:
            return True
        for idx, (lb, ub) in constraints.items():
            if w[idx] < lb or w[idx] > ub:
                return False
        return True

    for i in range(1, max_iter + 1):
        if cancel_cb and cancel_cb():
            break
        w = np.random.dirichlet(np.ones(n))
        if _satisfies(w):
            mse = compute_mse(w, values, target)
            if mse < best_mse:
                best_mse, best_w = mse, w
            if best_mse <= mse_threshold:
                if progress_cb:
                    progress_cb(i, best_mse)
                break
        if progress_cb:
            progress_cb(i, best_mse)
    if best_w is not None:
        return best_mse, best_w
    return None
