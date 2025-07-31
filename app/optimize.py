"""Core optimization helpers (updated to use database-driven workflow)."""

import itertools
import sys
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

# progress tracking shared by optimization routines
_PROGRESS = {"total": 0, "done": 0}

def get_progress() -> dict:
    """Return current optimization progress."""
    return dict(_PROGRESS)


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


def _is_valid_prop(col: str, limit: float) -> bool:
    num = _parse_numeric(col)
    return num is not None and num <= limit

def _get_materials_table(schema: Optional[str] = None):
    """Връща таблицата materials_grit за указаната или текущата схема."""


def _is_valid_prop(col: str, limit: float) -> bool:
    num = _parse_numeric(col)
    return num is not None and num <= limit

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

    target = np.mean(values, axis=0)

    return ids, values, target, numeric_cols


def load_recipe_data(
    property_limit: float,
    schema: Optional[str] = None,
    allowed_ids: Optional[list[int]] = None,
):
    """Load materials and numeric columns with optional limit and filtering."""

    tbl = _get_materials_table(schema)

    stmt = select(tbl)
    if 'user_id' in tbl.c:
        stmt = stmt.where(tbl.c.user_id == current_user.id)
    if allowed_ids:
        stmt = stmt.where(tbl.c.id.in_(allowed_ids))

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
    constraints: list[tuple[int, str, float]] | None = None,
) -> tuple[float, tuple[int, ...], np.ndarray] | None:
    """Optimize weights for a specific combination using multi-start SLSQP."""

    subset = values[list(combo)]

    # Convert global constraint indices to local positions
    local_cons = []
    if constraints:
        pos_map = {g_idx: i for i, g_idx in enumerate(combo)}
        for idx, op, val in constraints:
            if idx not in pos_map:
                continue
            loc = pos_map[idx]
            if op == '>':
                local_cons.append({'type': 'ineq', 'fun': lambda w, l=loc, v=val: w[l] - v})
            elif op == '<':
                local_cons.append({'type': 'ineq', 'fun': lambda w, l=loc, v=val: v - w[l]})
            elif op == '=':
                local_cons.append({'type': 'eq', 'fun': lambda w, l=loc, v=val: w[l] - v})

    out = optimize_with_restarts(subset, target, n_restarts, local_cons)
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
def optimize_with_restarts(
    values: np.ndarray,
    target: np.ndarray,
    n_restarts: int = 20,
    extra_cons: list[dict] | None = None,
):
    """Run SLSQP from multiple starting points and return the best result."""

    if minimize is None:
        raise RuntimeError("SciPy is required for continuous optimization")

    k = values.shape[0]

    def obj(w: np.ndarray) -> float:
        return compute_mse(w, values, target)

    bounds = [(0.0, 1.0)] * k
    cons = [{'type': 'eq', 'fun': lambda w: w.sum() - 1.0}]
    if extra_cons:
        cons.extend(extra_cons)

    inits = [np.full(k, 1.0 / k)]
    inits += list(np.random.dirichlet(np.ones(k), size=n_restarts))

    best = None
    for x0 in inits:
        res = minimize(
            obj,
            x0,
            method='SLSQP',
            bounds=bounds,
            constraints=cons,
            options={'ftol': 1e-9, 'eps': 1e-4, 'maxiter': 50000},
        )
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
                  constraints: list[tuple[int, str, float]] | None = None,
                  progress_cb=None,
                  ):
    """Evaluate all material combinations and return the best result."""

    n = values.shape[0]
    combos: list[tuple[int, ...]] = []
    for r in range(1, min(max_combo_num, n) + 1):
        combos.extend(itertools.combinations(range(n), r))
    total = len(combos)
    if progress_cb:
        progress_cb(0, total)

    best = None
    results: list[tuple[float, tuple[int, ...], np.ndarray]] = []
    for i, combo in enumerate(combos, 1):
        pct = i / total * 100
        sys.stdout.write(f"\rProgress: {pct:6.2f}% ({i}/{total})")
        sys.stdout.flush()
        if progress_cb:
            progress_cb(i, total)
        # Skip combos that don't contain materials from equality/">" constraints
        if constraints:
            required = {
                idx
                for idx, op, _ in constraints
                if op in ('=', '>')
            }
            if not required.issubset(set(combo)):
                continue

        res = optimize_combo(combo, values, target, n_restarts, constraints)
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
    material_ids: Optional[list[int]] = None,
    constraints: Optional[list[tuple[int, str, float]]] = None,
):
    """Load materials and search for the optimal mix."""

    # reset progress
    _PROGRESS["total"] = 0
    _PROGRESS["done"] = 0

    ids, names, values, target, prop_cols = load_recipe_data(
        property_limit, schema, material_ids
    )

    # Map DB id -> index in arrays
    id_to_idx = {mid: i for i, mid in enumerate(ids)}
    constr_idx: list[tuple[int, str, float]] = []
    if constraints:
        for mid, op, val in constraints:
            if mid in id_to_idx:
                constr_idx.append((id_to_idx[mid], op, float(val)))

    def progress_cb(done: int, total: int):
        _PROGRESS["total"] = int(total)
        _PROGRESS["done"] = int(done)

    best = find_best_mix(
        names,
        values,
        target,
        prop_cols,
        max_combo_num,
        mse_threshold,
        RESTARTS,
        constr_idx,
        progress_cb,
    )

    _PROGRESS["done"] = _PROGRESS.get("total", 0)

    if not best:
        return None
    # unpack the best result
    mse, combo, weights = best
    # compute the mixed profile
    # Use only the columns corresponding to the chosen materials for mixing
    mixed = weights.dot(values[list(combo)])

    return {
        # Convert NumPy integer IDs to plain Python ints for JSON serialization
        'material_ids': [int(ids[i]) for i in combo],
        'weights':      weights.tolist(),
        'best_mse':     mse,
        'prop_columns': prop_cols,
        'target_profile': target.tolist(),
        'mixed_profile':  mixed.tolist(),
    }
