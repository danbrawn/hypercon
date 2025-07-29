import itertools
import uuid
from threading import Thread, Lock

from .optimize import load_data, optimize_weights

# In‑memory job store
jobs = {}
jobs_lock = Lock()

def start_job(params):
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            'status':    'PENDING',
            'progress':  0,
            'best_mse':  None,
            'result':    None
        }
    # Launch background thread
    Thread(target=_run_job, args=(job_id, params), daemon=True).start()
    return job_id

def _run_job(job_id, params):
    # load_data returns (ids, values, target, prop_cols)
    ids, values, target, prop_cols = load_data(params)

    # generate all combos up to MAX_COMBINATIONS (or use all selected at once)
    combos = [
        combo
        for r in range(1, min(params.get('max_combo', len(ids)))+1)
        for combo in itertools.combinations(range(len(ids)), r)
    ]
    total = len(combos)
    best_mse = float('inf')
    best_combo = None
    best_weights = None

    for idx, combo in enumerate(combos, start=1):
        sub_vals = values[list(combo)]
        out = optimize_weights(sub_vals, target)
        if out:
            mse, weights = out
            if mse < best_mse:
                best_mse    = mse
                best_combo  = combo
                best_weights = weights

        # update in‑memory status
        with jobs_lock:
            jobs[job_id]['status']   = 'PROGRESS'
            jobs[job_id]['progress'] = int(idx/total*100)
            jobs[job_id]['best_mse'] = best_mse

        # early stop
        thr = params.get('mse_threshold')
        if thr is not None and best_mse <= thr:
            break

    # finalize
    with jobs_lock:
        jobs[job_id]['status'] = 'SUCCESS'
        jobs[job_id]['result'] = {
            'material_ids':  [ids[i] for i in best_combo],
            'weights':       best_weights.tolist(),
            'best_mse':      best_mse,
            'prop_columns':  prop_cols
        }
