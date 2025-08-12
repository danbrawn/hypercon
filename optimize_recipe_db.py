# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
CLI tool that optimizes a recipe using database data.

It loads materials from the ``materials_grit`` table, normalizes their
profiles, derives the target profile from numeric column names and tries all
combinations of the selected materials, using multi-start SLSQP to find the
best mix.
"""

import itertools
import sys
import numpy as np
from scipy.optimize import minimize

from app.optimize import (
    load_data as db_load_data,
    compute_profiles,
    etalon_from_columns,
    POWER,
)

# ---- Configuration ----
MSE_THRESHOLD = 1e-4   # early stop threshold
RESTARTS = 10          # number of SLSQP restarts
# -----------------------

def compute_mse(weights: np.ndarray, values: np.ndarray, target: np.ndarray) -> float:
    mix = weights.dot(values)
    return float(((mix - target) ** 2).mean())


def optimize_weights(values: np.ndarray, target: np.ndarray, n_restarts: int = RESTARTS):
    k = values.shape[0]
    best = None
    bounds = [(0.0, 1.0)] * k
    cons = ({'type': 'eq', 'fun': lambda w: w.sum() - 1.0},)

    inits = [np.full(k, 1.0 / k)]
    inits += list(np.random.dirichlet(np.ones(k), size=n_restarts))

    for x0 in inits:
        res = minimize(lambda w: compute_mse(w, values, target),
                       x0,
                       method='SLSQP',
                       bounds=bounds,
                       constraints=cons,
                       options={'ftol': 1e-9, 'maxiter': 50000})
        if not res.success:
            continue
        cand = (res.fun, res.x)
        if best is None or cand[0] < best[0]:
            best = cand
    return best


def find_best_mix(
    profiles: np.ndarray, target: np.ndarray, max_combo: int | None = None
):
    """Try all material combinations and return the lowest-MSE mix.

    If ``max_combo`` is ``None`` every subset of the provided materials is
    evaluated.
    """
    n = profiles.shape[0]
    limit = n if max_combo is None else min(max_combo, n)
    combos = [
        c for r in range(1, limit + 1) for c in itertools.combinations(range(n), r)
    ]
    total = len(combos)
    best = None

    for i, combo in enumerate(combos, 1):
        sys.stdout.write(f"\rProgress: {i}/{total} ({i/total*100:.1f}%)")
        sys.stdout.flush()
        subset = profiles[list(combo)]
        out = optimize_weights(subset, target)
        if not out:
            continue
        mse, weights = out
        if best is None or mse < best[0]:
            best = (mse, combo, weights)
        if mse <= MSE_THRESHOLD:
            print("\nThreshold reached, stopping.")
            break
    print()
    if not best:
        raise RuntimeError("No valid optimization result")
    return best


def main():
    ids, values, _, col_names = db_load_data()
    profiles = compute_profiles(values, power=POWER)
    target = etalon_from_columns(col_names, power=POWER)

    mse, combo, weights = find_best_mix(profiles, target)

    print(f"\nBest MSE: {mse:.6f}\n")
    print("Selected materials and proportions:")
    for idx, w in zip(combo, weights):
        print(f"  - id={ids[idx]}: {w*100:.2f}%")


if __name__ == '__main__':
    main()
