# app/optimize.py
import numpy as np
from scipy.optimize import minimize
from flask_login import current_user
from .models import db
from sqlalchemy import MetaData, Table, select

MAX_COMBINATIONS = 7
MSE_THRESHOLD   = 0.0004

def _is_number(val):
    try:
        float(val)
        return True
    except ValueError:
        return False

def load_data(params):
    """
    params must include:
      - selected_ids: list of material IDs
      - prop_min, prop_max: numeric bounds on which columns to include
      - target_profile: list of floats for the target
    """
    engine = db.get_engine()
    meta   = MetaData(bind=engine)
    # reflect the existing table
    materials = Table('materials_grit', meta, autoload_with=engine)

    # fetch only the selected rows for this user
    stmt = (
        select(materials)
        .where(materials.c.user_id == current_user.id)
        .where(materials.c.id.in_(params['selected_ids']))
    )
    rows = engine.execute(stmt).fetchall()
    if not rows:
        return [], np.empty((0,0)), np.array(params.get('target_profile', [])), []

    # figure out which numeric columns to use
    prop_cols = [
        c.name for c in materials.columns
        if _is_number(c.name)
        and params['prop_min'] <= float(c.name) <= params['prop_max']
    ]

    # build the (n_materials × n_props) matrix
    values = np.array(
        [[row[c] for c in prop_cols] for row in rows],
        dtype=float
    )
    target = np.array(params['target_profile'], dtype=float)
    ids    = [row['id'] for row in rows]

    return ids, values, target, prop_cols


def optimize_weights(values, target):
    """
    Single‐shot optimization over ALL selected materials.
    Returns (mse, weights) or None.
    """
    n = values.shape[0]
    if n == 0:
        return None
    p0     = np.full(n, 1.0/n)
    bounds = [(0,1)] * n
    cons   = {'type':'eq', 'fun': lambda w: w.sum() - 1.0}

    res = minimize(
        lambda w: np.mean((w.dot(values) - target)**2),
        p0, bounds=bounds, constraints=cons
    )
    return (res.fun, res.x) if res.success else None
