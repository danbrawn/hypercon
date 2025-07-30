# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""Quick standalone optimizer using Excel input.

This script loads material profiles and a target profile from an Excel sheet
and searches all material combinations up to ``MAX_COMBO``. For each subset it
runs SLSQP multiple times from random starting points to minimize the mean
square error between the mixed profile and the target. The top 10 results are
printed in ascending order of MSE.
"""

import itertools
import sys
from pathlib import Path
from typing import Iterable, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
EXCEL_FILE = 'Optimization_simple.xlsx'
SHEET_NAME = 'Sheet2'
PROPERTY_LIMIT = 1000.0      # use columns whose header number ≤ this limit
MAX_COMBO = 7                # maximum number of materials in a mix
MSE_THRESHOLD = 1e-4         # early stop if reached
RESTARTS = 10                # SLSQP restarts
# ---------------------------------------------------------------------------

def _is_number(col: str) -> bool:
    try:
        float(col)
        return True
    except Exception:
        return False


def load_data(path: str, sheet: str, prop_limit: float):
    df = pd.read_excel(path, sheet_name=sheet)
    names_col = df['material_name']
    non_null = names_col.notna()
    n_materials = non_null.sum()
    mat_df = df.iloc[0:n_materials].reset_index(drop=True)
    material_names = mat_df['material_name'].astype(str).values
    cols = [c for c in df.columns[2:] if _is_number(c) and float(c) <= prop_limit]
    values = mat_df[cols].astype(float).values
    target = df.iloc[n_materials][cols].astype(float).values
    return material_names, values, target


def compute_mse(weights: np.ndarray, values: np.ndarray, target: np.ndarray) -> float:
    mix = weights.dot(values)
    return float(np.mean((mix - target) ** 2))


def optimize_weights(values: np.ndarray, target: np.ndarray, n_restarts: int = RESTARTS):
    k = values.shape[0]

    def obj(w: np.ndarray) -> float:
        return compute_mse(w, values, target)

    bounds = [(0.0, 1.0)] * k
    cons = ({'type': 'eq', 'fun': lambda w: w.sum() - 1.0},)

    inits = [np.full(k, 1.0 / k)]
    inits += list(np.random.dirichlet(np.ones(k), size=n_restarts))

    best = None
    for x0 in inits:
        res = minimize(obj, x0, method='SLSQP', bounds=bounds,
                       constraints=cons,
                       options={'ftol': 1e-9, 'disp': False, 'maxiter': 50000})
        if not res.success:
            continue
        cand = (res.fun, res.x)
        if best is None or cand[0] < best[0]:
            best = cand
    return best


def search_all_combos(values: np.ndarray, target: np.ndarray) -> Iterable[Tuple[int, Tuple[int, ...], float, np.ndarray]]:
    n = values.shape[0]
    combos = [combo for r in range(1, min(MAX_COMBO, n) + 1)
              for combo in itertools.combinations(range(n), r)]
    total = len(combos)
    results = []
    for idx, combo in enumerate(combos, 1):
        sys.stdout.write(f"\r{idx}/{total} combos ({idx/total*100:.1f}%)")
        sys.stdout.flush()
        subvals = values[list(combo)]
        out = optimize_weights(subvals, target)
        if out:
            mse, w = out
            results.append((len(combo), combo, mse, w))
            if mse <= MSE_THRESHOLD:
                print("\nThreshold reached, stopping early.")
                break
    print()
    results.sort(key=lambda t: t[2])
    return results


def main(path: str = EXCEL_FILE, sheet: str = SHEET_NAME):
    names, values, target = load_data(path, sheet, PROPERTY_LIMIT)
    all_results = search_all_combos(values, target)
    print("\n--- Top 10 mixes by MSE ---")
    for size, combo, mse, w in all_results[:10]:
        mats = [names[i] for i in combo]
        w_str = ', '.join(f"{x:.2f}" for x in w)
        print(f"{size:>2}-mix: {mats!s:20s} -> MSE={mse:.6f}, w=[{w_str}]")

    if all_results:
        _, best_combo, best_mse, best_w = all_results[0]
        print(f"\nBest MSE={best_mse:.6f}")
        for idx, frac in zip(best_combo, best_w):
            print(f"  - {names[idx]}: {frac*100:.2f}%")


if __name__ == '__main__':
    main()
