from celery import Celery
from .optimize import (
    load_data,
    optimize_combo,
    MAX_COMBINATIONS,
    MSE_THRESHOLD,
)
from threading import Thread, Event
import uuid
from flask import current_app

celery = Celery(
    'hypercon',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1'
)

# ------------------ Local fallback job handling ------------------

class _LocalJob:
    def __init__(self, params):
        self.id = str(uuid.uuid4())
        self.params = params
        # Capture the current Flask app so the worker thread can push an
        # application context when accessing the database.
        self.app = current_app._get_current_object()
        self.status = 'PENDING'
        self.meta = {'current': 0, 'total': params.get('max_combinations', MAX_COMBINATIONS), 'best_mse': None}
        self.result = None
        self._cancel = Event()
        Thread(target=self._run, daemon=True).start()

    def cancel(self):
        self._cancel.set()

    def _run(self):
        # ``load_data`` and SQLAlchemy operations require an application context
        with self.app.app_context():
            max_comb = self.params.get('max_combinations', MAX_COMBINATIONS)
            mse_thresh = self.params.get('mse_threshold', MSE_THRESHOLD)
            try:
                ids, values, target, prop_cols, constraints = load_data(self.params)
            except Exception as exc:
                self.status = 'FAILURE'
                self.result = {'error': str(exc)}
                return
        progress = []

        def cb(step, best):
            self.status = 'PROGRESS'
            self.meta.update(current=step, best_mse=best)
            progress.append({'step': step, 'best_mse': best})

        try:
            out = optimize_combo(
                values,
                target,
                max_comb,
                mse_thresh,
                progress_cb=cb,
                constraints=constraints,
                cancel_cb=self._cancel.is_set,
            )
        except Exception as exc:
            self.status = 'FAILURE'
            self.result = {'error': str(exc), 'progress': progress}
            return

        if self._cancel.is_set():
            self.status = 'REVOKED'
            self.result = {'error': 'Cancelled', 'progress': progress}
            return
        if not out:
            self.status = 'FAILURE'
            self.result = {'error': 'Optimization failed', 'progress': progress}
            return

        mse, weights = out
        mixed_profile = (weights @ values).tolist()
        self.result = {
            'material_ids': ids,
            'weights': weights.tolist(),
            'mse': mse,
            'prop_columns': prop_cols,
            'mixed_profile': mixed_profile,
            'progress': progress,
        }
        self.status = 'SUCCESS'


_local_jobs = {}


def start_local_job(params) -> str:
    job = _LocalJob(params)
    _local_jobs[job.id] = job
    return job.id


def local_job_status(job_id):
    job = _local_jobs.get(job_id)
    if not job:
        return None
    resp = {'status': job.status}
    if job.status == 'PROGRESS':
        resp['meta'] = job.meta
    if job.status in {'SUCCESS', 'FAILURE', 'REVOKED'}:
        resp['result'] = job.result
    return resp


def cancel_local_job(job_id):
    job = _local_jobs.get(job_id)
    if not job:
        return False
    job.cancel()
    return True


@celery.task(bind=True)
def optimize_task(self, params):
    """Celery задача за оптимизация.

    params идва от фронтенда и съдържа selected_ids, constraints,
    prop_min и prop_max.
    """
    max_comb = params.get('max_combinations', MAX_COMBINATIONS)
    mse_thresh = params.get('mse_threshold', MSE_THRESHOLD)

    try:
        ids, values, target, prop_cols, constraints = load_data(params)
    except ValueError as exc:
        return {'error': str(exc)}

    progress = []

    update_enabled = getattr(getattr(self, 'request', None), 'id', None) is not None

    def cb(step, best):
        if update_enabled:
            self.update_state(state='PROGRESS', meta={'current': step, 'total': max_comb, 'best_mse': best})
        progress.append({'step': step, 'best_mse': best})

    out = optimize_combo(values, target, max_comb, mse_thresh, progress_cb=cb, constraints=constraints)
    if not out:
        return {'error': 'Optimization failed', 'progress': progress}
    mse, weights = out
    mixed_profile = (weights @ values).tolist()
    return {
        'material_ids': ids,
        'weights': weights.tolist(),
        'mse': mse,
        'prop_columns': prop_cols,
        'mixed_profile': mixed_profile,
        'progress': progress
    }
