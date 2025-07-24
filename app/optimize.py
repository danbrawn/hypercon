import numpy as np
from sqlalchemy import MetaData, Table, inspect, select
from flask import session
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

def _get_materials_table():
    """Връща таблицата materials_grit за текущата схема."""
    sch = session.get("schema") if current_user.role == "operator" else "main"
    meta = MetaData(schema=sch)
    return Table("materials_grit", meta, autoload_with=db.engine)

def load_data(params):
    """Чете данните за оптимизация от базата.

    Очаква params dict с ключове:
      - 'selected_ids': списък от избраните ID на материали
      - 'constraints': {material_id: (min, max), ...}  # засега не се ползва
      - 'prop_min', 'prop_max': граници за включване на колони

    Връща:
      - material_ids: list
      - property_values: np.ndarray(shape=(n, m))
      - target_profile: np.ndarray(length=m)  # средни стойности на избраните материали
      - prop_columns: list
    """
    tbl = _get_materials_table()

    numeric_cols = [c.key for c in tbl.columns if _is_number(c.key)]
    numeric_cols.sort(key=lambda k: _parse_numeric(k))
    prop_cols = [c for c in numeric_cols
                 if params['prop_min'] <= _parse_numeric(c) <= params['prop_max']]

    stmt = select(tbl).where(tbl.c.id.in_(params['selected_ids']))
    rows = db.session.execute(stmt).mappings().all()

    values = np.array([[row[c] for c in prop_cols] for row in rows], dtype=float)
    target = np.mean(values, axis=0)
    ids = [row['id'] for row in rows]

    return ids, values, target, prop_cols

def compute_mse(weights, values, target):
    mixed = np.dot(weights, values)
    return float(np.mean((mixed - target) ** 2))

def optimize_combo(
    values,
    target,
    max_iter: int = MAX_COMBINATIONS,
    mse_threshold: float = MSE_THRESHOLD,
    progress_cb=None,
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
    """
    n = values.shape[0]
    best_mse = float("inf")
    best_w = None
    for i in range(1, max_iter + 1):
        w = np.random.dirichlet(np.ones(n))
        mse = compute_mse(w, values, target)
        if mse < best_mse:
            best_mse, best_w = mse, w
        if progress_cb:
            progress_cb(i, best_mse)
        if best_mse <= mse_threshold:
            break
    if best_w is not None:
        return best_mse, best_w
    return None
