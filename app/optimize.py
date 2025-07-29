import numpy as np
from sqlalchemy import MetaData, Table, inspect, select
from flask import session, has_request_context
from typing import Optional
from flask_login import current_user
import itertools

from . import db

# ==== Параметри ==== #
MAX_ITERATIONS  = 7        # брой тегления на случайни комбинации
MAX_COMPONENTS  = 3        # максимален брой материали в сместа
MSE_THRESHOLD   = 0.0004
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
    max_iter: int = MAX_ITERATIONS,
    mse_threshold: float = MSE_THRESHOLD,
    max_components: int = MAX_COMPONENTS,
    progress_cb=None,
    constraints=None,
    cancel_cb=None,
):
    """Search over all combinations of materials and optimize weights.

    For every subset of materials up to ``max_components`` elements,
    random search is performed over ``max_iter`` weight vectors. The
    subset/weights pair with the lowest mean squared error to the target
    profile is returned. The process stops early if a combination reaches
    ``mse_threshold``

    Parameters
    ----------
    values : np.ndarray
        Matrix with material properties.
    target : np.ndarray
        Desired property profile.
    max_iter : int
        How many random weight samples to try for each material subset.
    mse_threshold : float
        Stop early if a combination reaches this MSE.
    max_components : int
        Maximum number of materials allowed in a mixture.
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

    def _subset_valid(sub):
        if not constraints:
            return True
        share = 1.0 / len(sub)
        for idx, (lb, ub) in constraints.items():
            if idx in sub:
                if share < lb or share > ub:
                    return False
            else:
                if lb > 0:
                    return False
        return True

    def _weights_valid(sub, w_sub):
        if not constraints:
            return True
        pos = {idx: i for i, idx in enumerate(sub)}
        for idx, (lb, ub) in constraints.items():
            if idx in pos:
                val = w_sub[pos[idx]]
                if val < lb or val > ub:
                    return False
            else:
                if lb > 0:
                    return False
        return True

    max_components = min(max_components, n)

    for k in range(1, max_components + 1):
        for combo in itertools.combinations(range(n), k):
            if not _subset_valid(combo):
                continue
            for i in range(1, max_iter + 1):
                if cancel_cb and cancel_cb():
                    return None
                step += 1
                w_sub = np.random.dirichlet(np.ones(k))
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
