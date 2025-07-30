"""Core optimization helpers (updated to use database-driven workflow)."""

import itertools
import sys
import numpy as np
from typing import Optional
from scipy.optimize import minimize
from sqlalchemy import MetaData, Table, select
from flask import session, has_request_context
from flask_login import current_user

from . import db

# Configuration constants
POWER = 0.217643428858232      # exponent for normalization (from Excel)
MAX_COMPONENTS = 7             # max number of materials in a mix
MSE_THRESHOLD = 1e-4           # early stopping threshold for MSE
RESTARTS = 10                  # number of SLSQP restarts

# Utility to parse numeric column names
import re
NUM_RE = re.compile(r'^\d+(?:\.\d+)?')

def _parse_numeric(val: str) -> Optional[float]:
    if val is None:
        return None
    m = NUM_RE.match(str(val))
    return float(m.group(0)) if m else None

def _is_number(val: str) -> bool:
    return _parse_numeric(val) is not None

# Load materials data from the DB
def _get_materials_table(schema: Optional[str] = None):
    if schema:
        sch = schema
    elif has_request_context() and getattr(current_user, 'role', None) == 'operator':
        sch = session.get('schema', 'main')
    else:
        sch = 'main'
    meta = MetaData(schema=sch)
    return Table('materials_grit', meta, autoload_with=db.engine)

def load_data(schema: Optional[str] = None):
    tbl = _get_materials_table(schema)
    # pick numeric columns
    numeric_cols = [c.key for c in tbl.columns if _is_number(c.key)]
    numeric_cols.sort(key=lambda k: _parse_numeric(k))

    stmt = select(tbl)
    if 'user_id' in tbl.c:
        stmt = stmt.where(tbl.c.user_id == current_user.id)
    rows = db.session.execute(stmt).mappings().all()

    if not rows:
        raise ValueError('Не са намерени материали за оптимизиране')
    if not numeric_cols:
        raise ValueError('Няма подходящи числови колони')

    # build arrays
    values = np.array([[row[c] for c in numeric_cols] for row in rows], dtype=float)
    ids = [row['id'] for row in rows]
    return ids, values, numeric_cols

# Normalization routines
def compute_profiles(values: np.ndarray, power: float = POWER) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    mn = values.min(axis=0)
    mx = values.max(axis=0)
    num = values**power - mn**power
    denom = mx**power - mn**power
    denom[denom == 0] = 1.0
    return num / denom

# Build target (etalon) from column names
def etalon_from_columns(columns: list[str], power: float = POWER) -> np.ndarray:
    nums = np.array([_parse_numeric(c) for c in columns], dtype=float)
    mn, mx = nums.min(), nums.max()
    if mx == mn:
        return np.zeros_like(nums)
    return (nums**power - mn**power) / (mx**power - mn**power)

# MSE objective
def compute_mse(weights: np.ndarray,
                values: np.ndarray,
                target: np.ndarray) -> float:
    mix = weights.dot(values)
    return float(np.mean((mix - target)**2))

# Continuous optimization with restarts to avoid local minima
def optimize_with_restarts(values: np.ndarray,
                           target: np.ndarray,
                           n_restarts: int = RESTARTS):
    k = values.shape[0]
    bounds = [(0.0, 1.0)] * k
    cons = ({'type': 'eq', 'fun': lambda w: w.sum() - 1.0},)
    best = None

    # initial uniform guess + random restarts
    inits = [np.full(k, 1.0/k)]
    inits += list(np.random.dirichlet(np.ones(k), size=n_restarts))

    for x0 in inits:
        res = minimize(lambda w: compute_mse(w, values, target),
                       x0,
                       method='SLSQP',
                       bounds=bounds,
                       constraints=cons,
                       options={'ftol':1e-9, 'maxiter':50000})
        if not res.success:
            continue
        cand = (res.fun, res.x)
        if best is None or cand[0] < best[0]:
            best = cand
    return best

# Search best subset of materials
def find_best_mix(values: np.ndarray,
                  target: np.ndarray,
                  max_components: int = MAX_COMPONENTS) -> tuple:
    n = values.shape[0]
    combos = [combo
              for r in range(1, min(max_components, n) + 1)
              for combo in itertools.combinations(range(n), r)]

    best = None
    total = len(combos)
    for i, combo in enumerate(combos, 1):
        sys.stdout.write(f"\rProgress: {i}/{total} ({i/total*100:.1f}%)")
        sys.stdout.flush()
        subvals = values[list(combo)]
        out = optimize_with_restarts(subvals, target)
        if out:
            mse, weights = out
            if best is None or mse < best[0]:
                best = (mse, combo, weights)
            if mse <= MSE_THRESHOLD:
                print("\nThreshold reached, stopping.")
                break
    print()
    if not best:
        raise RuntimeError('Няма успешно решение за оптимизация')
    return best

# Full optimization pipeline
def run_full_optimization(schema: Optional[str] = None):
    ids, raw_values, col_names = load_data(schema)
    profiles = compute_profiles(raw_values)
    etalon = etalon_from_columns(col_names)

    mse, combo, weights = find_best_mix(profiles, etalon)
    mixed = weights.dot(profiles[list(combo)])

    return {
        'material_ids':   [ids[i] for i in combo],
        'weights':        weights.tolist(),
        'best_mse':       mse,
        'prop_columns':   col_names,
        'target_profile': etalon.tolist(),
        'mixed_profile':  mixed.tolist(),
    }
