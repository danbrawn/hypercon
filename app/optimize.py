import numpy as np
from sqlalchemy import MetaData, Table, inspect, select
from flask import session, has_request_context
from typing import Optional
from flask_login import current_user
from scipy.optimize import minimize

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

def optimize_weights(values, target):
    """
    Given:
      values: np.array shape (n_materials, n_props)
      target: np.array length n_props
    Returns:
      (mse, weights) or None
    """
    n = values.shape[0]
    p0 = np.full(n, 1/n)
    bounds = [(0,1)] * n
    cons = {'type': 'eq', 'fun': lambda w: w.sum() - 1}
    res = minimize(lambda w: np.mean((w.dot(values) - target)**2),
                   p0, bounds=bounds, constraints=cons)
    return (res.fun, res.x) if res.success else None