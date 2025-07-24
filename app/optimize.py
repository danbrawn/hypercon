import numpy as np
from scipy.optimize import minimize
from sqlalchemy import MetaData, Table, inspect, select
from flask import session
from flask_login import current_user

from . import db

# ==== Параметри ==== #
MAX_COMBINATIONS = 7
MSE_THRESHOLD = 0.0004
# ==================== #

def _is_number(val: str) -> bool:
    try:
        float(val)
        return True
    except Exception:
        return False

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
      - 'target_profile': желан профил за смесване

    Връща:
      - material_ids: list
      - property_values: np.ndarray(shape=(n, m))
      - target_profile: np.ndarray(length=m)
      - prop_columns: list
    """
    tbl = _get_materials_table()

    numeric_cols = [c.key for c in tbl.columns if _is_number(c.key)]
    prop_cols = [c for c in numeric_cols
                 if params['prop_min'] <= float(c) <= params['prop_max']]

    stmt = select(tbl).where(tbl.c.id.in_(params['selected_ids']))
    rows = db.session.execute(stmt).mappings().all()

    values = np.array([[row[c] for c in prop_cols] for row in rows], dtype=float)
    target = np.array(params['target_profile'], dtype=float)
    ids = [row['id'] for row in rows]

    return ids, values, target, prop_cols

def compute_mse(weights, values, target):
    mixed = np.dot(weights, values)
    return float(np.mean((mixed - target) ** 2))

def optimize_combo(values, target):
    n = values.shape[0]
    p0 = np.full(n, 1.0 / n)
    bounds = [(0.0, 1.0)] * n
    cons = {'type': 'eq', 'fun': lambda w: w.sum() - 1.0}
    res = minimize(compute_mse, p0, args=(values, target),
                   bounds=bounds, constraints=cons)
    if res.success:
        return res.fun, res.x
    return None
