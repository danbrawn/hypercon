
"""Core optimization helpers."""

import numpy as np
import pandas as pd

from sqlalchemy import MetaData, Table, select
from flask import session, has_request_context
from flask_login import current_user
from typing import Optional
import re
import itertools
import sys

try:  # SciPy is optional during development
    from scipy.optimize import minimize
except Exception:  # pragma: no cover
    minimize = None

from . import db

# Степента за нормализация на профилите
# Изведена от предоставените Excel формули
POWER = 0.217643428858232
MAX_COMPONENTS = 7  # maximum number of materials considered in a mix
RESTARTS = 10       # number of random restarts for SLSQP
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


def _is_valid_prop(col: str, limit: float) -> bool:
    num = _parse_numeric(col)
    return num is not None and num <= limit

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


def load_recipe_data(property_limit: float, schema: Optional[str] = None):
    """Load materials and numeric columns with optional limit."""

    tbl = _get_materials_table(schema)

    stmt = select(tbl)
    if 'user_id' in tbl.c:
        stmt = stmt.where(tbl.c.user_id == current_user.id)

    df = pd.read_sql(stmt, db.engine)
    df = df.replace(r'^\s*$', np.nan, regex=True)

    ids = df['id'].astype(int).values
    material_names = df['material_name'].astype(str).values

    props = [c for c in df.columns if _is_valid_prop(c, property_limit)]
    num_df = df[props].apply(pd.to_numeric, errors='coerce').fillna(0.0)
    material_values = num_df.values

    target_norm = etalon_from_columns(props)

    return ids, material_names, material_values, target_norm, props

def compute_mse(weights, values, target):
    mixed = np.dot(weights, values)
    return float(np.mean((mixed - target) ** 2))


def objective(w: np.ndarray, values: np.ndarray, target: np.ndarray) -> float:
    """Objective function for SLSQP."""
    return compute_mse(w, values, target)


def optimize_combo(
    combo: tuple[int, ...],
    values: np.ndarray,
    target: np.ndarray,
    n_restarts: int = 20,
) -> tuple[float, tuple[int, ...], np.ndarray] | None:
    """Optimize weights for a specific combination using multi-start SLSQP."""

    subset = values[list(combo)]
    out = optimize_with_restarts(subset, target, n_restarts)
    if not out:
        return None
    mse, weights = out
    return mse, combo, weights


def compute_profiles(values: np.ndarray, power: float = POWER) -> np.ndarray:
    """Return normalized profiles using global column ranges."""

    values = np.asarray(values, dtype=float)

    mn = values.min(axis=0)
    mx = values.max(axis=0)

    num = values ** power - mn ** power
    denom = mx ** power - mn ** power
    denom[denom == 0] = 1.0

    return num / denom


def normalize_row(row: np.ndarray, power: float = POWER) -> np.ndarray:
    """Normalize a numeric row using the specified exponent."""
    row = np.asarray(row, dtype=float)
    mn = row.min()
    mx = row.max()
    if mx == mn:
        return np.zeros_like(row)
    return (row ** power - mn ** power) / (mx ** power - mn ** power)


def etalon_from_columns(columns: list[str], power: float = POWER) -> np.ndarray:
    """Return normalized profile computed only from column names."""
    nums = np.array([_parse_numeric(c) for c in columns], dtype=float)
    return normalize_row(nums, power)



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


def optimize_with_restarts(values: np.ndarray,
                           target: np.ndarray,
                           n_restarts: int = 20):
    """Run SLSQP from multiple starting points and return the best result."""

    if minimize is None:
        raise RuntimeError("SciPy is required for continuous optimization")

    k = values.shape[0]

    def obj(w: np.ndarray) -> float:
        return compute_mse(w, values, target)

    bounds = [(0.0, 1.0)] * k
    cons = ({'type': 'eq', 'fun': lambda w: w.sum() - 1.0},)

    inits = [np.full(k, 1.0 / k)]
    inits += list(np.random.dirichlet(np.ones(k), size=n_restarts))

    best = None
    for x0 in inits:
        res = minimize(obj, x0,
                       method='SLSQP',
                       bounds=bounds,
                       constraints=cons,
                       options={'ftol': 1e-9, 'eps': 1e-4, 'maxiter': 50000})
        if not res.success:
            continue
        cand = (res.fun, res.x)
        if best is None or cand[0] < best[0]:
            best = cand

    return best


def find_best_mix(names: np.ndarray,
                  values: np.ndarray,
                  target: np.ndarray,
                  props: list[str],
                  max_combo_num: int,
                  mse_threshold: float | None = None,
                  n_restarts: int = RESTARTS,
                  ):
    """Evaluate all material combinations and return the best result."""

    n = values.shape[0]
    combos: list[tuple[int, ...]] = []
    for r in range(1, min(max_combo_num, n) + 1):
        combos.extend(itertools.combinations(range(n), r))
    total = len(combos)

    best = None
    results: list[tuple[float, tuple[int, ...], np.ndarray]] = []
    for i, combo in enumerate(combos, 1):
        pct = i / total * 100
        sys.stdout.write(f"\rProgress: {pct:6.2f}% ({i}/{total})")
        sys.stdout.flush()
        res = optimize_combo(combo, values, target, n_restarts)
        if res:
            results.append(res)
            mse_val, combo_idx, frac_vals = res
            combo_names = [names[j] for j in combo_idx]
            frac_str = ", ".join(
                [f"{names[j]}: {f*100:.2f}%" for j, f in zip(combo_idx, frac_vals)]
            )
            print(
                f"\nMSE: {mse_val:.6f} | Комбо: [{', '.join(combo_names)}] | Пропорции: [{frac_str}]"
            )
            if mse_threshold is not None and mse_val <= mse_threshold:
                best = res
                sys.stdout.write("Threshold reached, stopping early.\n")
                break
    sys.stdout.write("\n")
    if not results:
        raise RuntimeError('Няма успешно решение за оптимизация')
    if best is None:
        best = min(results, key=lambda t: t[0])
    return best

def run_full_optimization(
    schema: Optional[str] = None,
    property_limit: float = 1000.0,
    max_combo_num: int = MAX_COMPONENTS,
    mse_threshold: float | None = 0.0004,
):
    """Load materials and search for the optimal mix."""

    ids, names, values, target, prop_cols = load_recipe_data(property_limit, schema)

    best = find_best_mix(names, values, target, prop_cols,
                         max_combo_num, mse_threshold, RESTARTS)
    if not best:
        return None

    mse, combo, weights = best
    mixed = np.dot(weights, values[list(combo)])
    return {
        'material_ids': [ids[i] for i in combo],
        'weights':      weights.tolist(),
        'best_mse':     mse,
        'prop_columns': prop_cols,
        'target_profile': target.tolist(),
        'mixed_profile':  mixed.tolist(),
    }
