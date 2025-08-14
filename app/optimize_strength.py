# -*- coding: utf-8 -*-
"""
Optimize w_c and stah to reach target Flt_SP.
Deps: pip install pandas numpy sqlalchemy psycopg2-binary scipy
"""

import os
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from scipy.optimize import minimize

# -------------------------
# DB config
# -------------------------
PG_USER = os.getenv("PGUSER", "postgres")
PG_PASS = os.getenv("PGPASSWORD", "postgres")
PG_HOST = os.getenv("PGHOST", "localhost")
PG_PORT = os.getenv("PGPORT", "5432")
PG_DB   = os.getenv("PGDATABASE", "postgres")

ENGINE = create_engine(
    f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}",
    pool_pre_ping=True,
)

# -------------------------
# Global bounds (requested)
# -------------------------
W_C_LOW  = 0.05
W_C_HIGH = 1
STAH_LOW = 0
STAH_HIGH = 1  # mass bounds for stah (absolute)

# NEW: ratio bounds for stah_per_total
STAH_RATIO_LOW  = 0.04
STAH_RATIO_HIGH = 0.08  # i.e., 0% .. 8%
Flt_SP = 130.0  # target

# -------------------------
# Load data
# -------------------------
def load_data():
    df_t1 = pd.read_sql("SELECT * FROM public.materials_opt2", ENGINE)
    df_t2 = pd.read_sql("SELECT * FROM public.additives_opt2", ENGINE)

    # Ensure numeric dtypes
    for col in ["recipe", "spg", "kwa", "is_cement", "is_binder", "is_min_water", "is_max_water", "is_micro_sil"]:
        if col in df_t1.columns:
            df_t1[col] = pd.to_numeric(df_t1[col], errors="coerce").fillna(0.0)

    for col in ["recipe", "spg", "dry_cont"]:
        if col in df_t2.columns:
            df_t2[col] = pd.to_numeric(df_t2[col], errors="coerce").fillna(0.0)

    return df_t1, df_t2

# -------------------------
# Core computations
# -------------------------
def compute_all(df_t1_raw: pd.DataFrame, df_t2_raw: pd.DataFrame, w_c: float, stah: float, fcem: float = 60.0):
    """
    Returns dict with all intermediate values + Flt.
    Does not modify original DataFrames.
    """
    df_t1 = df_t1_raw.copy()
    df_t2 = df_t2_raw.copy()

    # t1 derived
    df_t1["w1000"] = df_t1["recipe"] * 1000.0
    df_t1["volume"] = np.where(df_t1["spg"] > 0, df_t1["w1000"] / df_t1["spg"], 0.0)
    df_t1["needed_w"] = df_t1["volume"] * df_t1["kwa"]

    # binder (as in your last version): sum of w1000 where is_binder>0
    binder = df_t1.loc[df_t1["is_binder"] > 0, "w1000"].sum()

    # t2 derived
    df_t2["weight"] = df_t2["recipe"] * binder
    df_t2["volume"] = np.where(df_t2["spg"] > 0, df_t2["weight"] / df_t2["spg"], 0.0)
    df_t2["water"]  = df_t2["weight"] * (1.0 - df_t2["dry_cont"])

    # sums
    volume_sum_t1 = df_t1["volume"].sum()
    volume_sum_t2 = df_t2["volume"].sum()

    # cement sums
    sum_w1000_cement = df_t1.loc[df_t1["is_cement"] > 0, "w1000"].sum()
    sum_recipe_cement = df_t1.loc[df_t1["is_cement"] > 0, "recipe"].sum()

    if sum_w1000_cement <= 0 or sum_recipe_cement <= 0:
        raise ValueError("No valid cement rows (is_cement>0) or sums are zero.")

    # waters
    total_w_1000 = w_c * sum_w1000_cement
    total_w      = w_c * sum_recipe_cement
    addit_water_sum = df_t2["water"].sum()

    max_w = total_w_1000 - addit_water_sum
    hyper1 = max_w + volume_sum_t1 + volume_sum_t2

    k_volume = (1000.0 / hyper1) * (1.0 - 0.04)  # 4% air

    needed_w_sum = df_t1["needed_w"].sum()
    min_w = needed_w_sum + addit_water_sum

    denom_min_w = df_t1.loc[df_t1["is_min_water"] > 0, "w1000"].sum()
    denom_max_w = df_t1.loc[df_t1["is_max_water"] > 0, "w1000"].sum()

    hyper3 = (min_w + addit_water_sum) / denom_min_w if denom_min_w > 0 else np.inf
    hyper2 = (max_w + addit_water_sum) / denom_max_w if denom_max_w > 0 else np.inf

    hyper4 = total_w_1000 * k_volume  # W

    # row totals
    df_t1["total_weight_k"] = df_t1["w1000"] * k_volume
    df_t2["total_weight_k"] = df_t2["weight"] * k_volume

    total_weight = df_t1["total_weight_k"].sum() + df_t2["total_weight_k"].sum() + hyper4

    # composition
    Cim = df_t1.loc[df_t1["is_cement"] > 0, "total_weight_k"].sum()
    ms  = df_t1.loc[df_t1["is_micro_sil"] > 0, "total_weight_k"].sum()

    if Cim <= 0:
        raise ValueError("Cim (sum total_weight_k where is_cement>0) is zero; cannot compute Flt.")

    # stah-related
    stah_per_total = 100*stah / total_weight
    Ps = stah / Cim * 100  # as in your last version

    # constants and factors
    Kk  = 3.49338462
    Ksz = 1.06
    t   = 28.0
    Kt  = 1.0 - np.exp(-(((t - 0.9) / 3.0) ** 0.6))  # not used in Flt yet
    Kfr = np.exp(0.034 * Ps)

    # water-cement relations
    W = hyper4
    twenty_two_ms = 0.22 * ms
    A = W / (Cim + twenty_two_ms)
    B = np.exp(-11.0 * ms / Cim) if Cim > 0 else 0.0
    C = 1.4 * A / (1.4 - 0.4 * B)

    Flt = Kk * Kfr * Ksz * fcem / ((1.0 + C) ** 2)

    return {
        "df_t1": df_t1,
        "df_t2": df_t2,
        "binder": binder,
        "volume_sum_t1": volume_sum_t1,
        "volume_sum_t2": volume_sum_t2,
        "w_c": w_c,
        "stah": stah,
        "total_w_1000": total_w_1000,
        "total_w": total_w,
        "addit_water_sum": addit_water_sum,
        "max_w": max_w,
        "hyper1": hyper1,
        "k_volume": k_volume,
        "needed_w_sum": needed_w_sum,
        "min_w": min_w,
        "hyper3": hyper3,
        "hyper2": hyper2,
        "hyper4": hyper4,
        "total_weight": total_weight,
        "stah_per_total": stah_per_total,
        "Kk": Kk,
        "Ksz": Ksz,
        "Kt": Kt,
        "Kfr": Kfr,
        "fcem": fcem,
        "Cim": Cim,
        "Ps": Ps,
        "ms": ms,
        "A": A,
        "B": B,
        "C": C,
        "Flt": Flt,
    }

# -------------------------
# Optimization
# -------------------------
def optimize_to_Flt(df_t1, df_t2, Flt_SP, fcem=60.0,
                    w_c_low=W_C_LOW, w_c_high=W_C_HIGH,
                    stah_low=STAH_LOW, stah_high=STAH_HIGH,
                    stah_ratio_low=STAH_RATIO_LOW, stah_ratio_high=STAH_RATIO_HIGH):
    """
    Minimize (Flt - Flt_SP)^2 under constraints:
      - w_c_low ≤ w_c ≤ w_c_high
      - stah_low ≤ stah ≤ stah_high
      - stah_ratio_low ≤ stah_per_total ≤ stah_ratio_high
    Returns (scipy result, computed dict).
    """

    # Initial guess
    x0 = np.array([(w_c_low + w_c_high) / 2.0, max(stah_low, 0.05)], dtype=float)

    # Objective
    def objective(x):
        w_c, stah = x
        try:
            out = compute_all(df_t1, df_t2, w_c=float(w_c), stah=float(stah), fcem=fcem)
        except ValueError:
            return 1e12
        return (out["Flt"] - Flt_SP) ** 2

    # Inequalities for stah_per_total (inclusive):
    # stah_per_total ≤ stah_ratio_high  =>  stah_ratio_high - stah_per_total ≥ 0
    def ineq_stah_ratio_max(x):
        w_c, stah = x
        try:
            out = compute_all(df_t1, df_t2, w_c=float(w_c), stah=float(stah), fcem=fcem)
        except ValueError:
            return -1.0
        return stah_ratio_high - out["stah_per_total"]

    # stah_per_total ≥ stah_ratio_low   =>  stah_per_total - stah_ratio_low ≥ 0
    def ineq_stah_ratio_min(x):
        w_c, stah = x
        try:
            out = compute_all(df_t1, df_t2, w_c=float(w_c), stah=float(stah), fcem=fcem)
        except ValueError:
            return -1.0
        return out["stah_per_total"] - stah_ratio_low

    # Bounds (absolute)
    bounds = ((w_c_low, w_c_high),
              (stah_low, stah_high if stah_high is not None else None))

    constraints = [
        {"type": "ineq", "fun": ineq_stah_ratio_max},
        {"type": "ineq", "fun": ineq_stah_ratio_min},
    ]

    res = minimize(
        objective,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 500, "ftol": 1e-12, "disp": False},
    )

    w_c_opt, stah_opt = res.x
    out = compute_all(df_t1, df_t2, w_c=float(w_c_opt), stah=float(stah_opt), fcem=fcem)
    out["success"] = bool(res.success)
    out["message"] = res.message
    out["nfev"] = res.nfev
    out["opt_w_c"] = float(w_c_opt)
    out["opt_stah"] = float(stah_opt)
    out["objective"] = float((out["Flt"] - Flt_SP) ** 2)

    return res, out

# -------------------------
# Run example
# -------------------------
if __name__ == "__main__":
    df_t1, df_t2 = load_data()
    res, out = optimize_to_Flt(
        df_t1, df_t2,
        Flt_SP=Flt_SP,
        fcem=60.0,
        w_c_low=W_C_LOW, w_c_high=W_C_HIGH,
        stah_low=STAH_LOW, stah_high=STAH_HIGH,
        stah_ratio_low=STAH_RATIO_LOW, stah_ratio_high=STAH_RATIO_HIGH
    )

    print("=== Optimization Results ===")
    print("Success:", out["success"], "|", out["message"])
    print("Function evaluations:", out["nfev"])
    print(f"Target Flt_SP  = {Flt_SP:.6g}")
    print(f"Achieved Flt   = {out['Flt']:.6g}")
    print(f"Objective (MSE)= {out['objective']:.6g}")
    print(f"Optimal w_c    = {out['opt_w_c']:.6g}  (bounds: {W_C_LOW}..{W_C_HIGH})")
    print(f"Optimal stah   = {out['opt_stah']:.6g}  (bounds: {STAH_LOW}..{STAH_HIGH})")
    print(f"stah/total     = {out['stah_per_total']:.6g}  (ratio bounds: {STAH_RATIO_LOW}..{STAH_RATIO_HIGH})")
    print(f"Cim            = {out['Cim']:.6g}")
    print(f"ms             = {out['ms']:.6g}")
    print(f"k_volume       = {out['k_volume']:.6g}")
    print(f"total_weight   = {out['total_weight']:.6g}")
    print(f"hyper2         = {out['hyper2']}")
    print(f"hyper3         = {out['hyper3']}")
