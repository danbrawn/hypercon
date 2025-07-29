# app/optimize_jobs.py
import itertools, uuid
from threading import Thread, Lock

# ``optimize_continuous`` is the replacement for the old ``optimize_weights``
# function that used SciPy's SLSQP solver. ``load_data`` now returns a
# constraints mapping as well, so we adjust the job runner accordingly.
from .optimize import load_data, optimize_continuous

jobs      = {}
jobs_lock = Lock()

def start_job(params):
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            'status':   'PENDING',
            'progress': 0,
            'best_mse': None,
            'result':   None
        }
    Thread(target=_run, args=(job_id, params), daemon=True).start()
    return job_id

def _run(job_id, params):
    ids, values, target, prop_cols, constraints = load_data(params)
    combos = [
        combo
        for r in range(1, min(params.get('max_combo', len(ids))) + 1)
        for combo in itertools.combinations(range(len(ids)), r)
    ]
    total     = len(combos)
    best_mse  = float('inf')
    best_combo = best_weights = None

    for idx, combo in enumerate(combos, start=1):
        subvals = values[list(combo)]
        sub_constraints = {
            pos: constraints[idx]
            for pos, idx in enumerate(combo)
            if idx in constraints
        }
        out = optimize_continuous(subvals, target, constraints=sub_constraints)
        if out:
            mse, weights = out
            if mse < best_mse:
                best_mse, best_combo, best_weights = mse, combo, weights

        with jobs_lock:
            jobs[job_id].update({
                'status':   'PROGRESS',
                'progress': int(idx/total*100),
                'best_mse': best_mse
            })

        if params.get('mse_threshold') is not None and best_mse <= params['mse_threshold']:
            break

    with jobs_lock:
        jobs[job_id].update({
            'status': 'SUCCESS',
            'result': {
                'material_ids': [ids[i] for i in best_combo],
                'weights':      best_weights.tolist(),
                'best_mse':     best_mse,
                'prop_columns': prop_cols,
                'target_profile': target.tolist()
            }
        })
