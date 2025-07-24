from celery import Celery
from .optimize import load_data, optimize_combo, MAX_COMBINATIONS, MSE_THRESHOLD

celery = Celery(
    'hypercon',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1'
)

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
