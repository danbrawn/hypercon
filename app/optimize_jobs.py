# app/optimize_jobs.py
import uuid
from threading import Lock

from .optimize import (
    load_data,
    find_best_mix,
    MSE_THRESHOLD,
    MAX_COMPONENTS,
)

jobs      = {}
jobs_lock = Lock()

def start_job(params):
    """Run optimization synchronously and store the result."""
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            'status':   'RUNNING',
            'progress': 0,
            'best_mse': None,
            'result':   None,
        }
    _run(job_id, params)
    return job_id

def _run(job_id, params):
    try:
        ids, values, target, prop_cols, constraints = load_data(params)
    except Exception as exc:
        with jobs_lock:
            jobs[job_id].update({'status': 'FAILURE', 'result': {'error': str(exc)}})
        return

    max_combo     = params.get('max_combo', MAX_COMPONENTS)
    mse_threshold = params.get('mse_threshold', MSE_THRESHOLD)

    def cb(step, total, best):
        with jobs_lock:
            jobs[job_id].update({
                'status':   'RUNNING',
                'progress': int(step / total * 100),
                'best_mse': best,
            })

    result = find_best_mix(
        values,
        target,
        max_components=max_combo,
        mse_threshold=mse_threshold,
        constraints=constraints,
        progress_cb=cb,
    )

    if not result:
        with jobs_lock:
            jobs[job_id].update({'status': 'FAILURE', 'result': {'error': 'Optimization failed'}})
        return

    mse, combo, weights = result
    with jobs_lock:
        jobs[job_id].update({
            'status': 'SUCCESS',
            'result': {
                'material_ids': [ids[i] for i in combo],
                'weights':      weights.tolist(),
                'best_mse':     mse,
                'prop_columns': prop_cols,
                'target_profile': target.tolist(),
            }
        })
