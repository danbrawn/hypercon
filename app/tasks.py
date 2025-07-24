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
    prop_min, prop_max и target_profile.
    """
    max_comb = params.get('max_combinations', MAX_COMBINATIONS)
    mse_thresh = params.get('mse_threshold', MSE_THRESHOLD)

    try:
        ids, values, target, prop_cols = load_data(params)
    except ValueError as exc:
        return {'error': str(exc)}

    progress = []

    def cb(step, best):
        self.update_state(state='PROGRESS', meta={'current': step, 'total': max_comb, 'best_mse': best})
        progress.append({'step': step, 'best_mse': best})

    out = optimize_combo(values, target, max_comb, mse_thresh, progress_cb=cb)
    if not out:
        return {'error': 'Optimization failed', 'progress': progress}
    mse, weights = out
    return {
        'material_ids': ids,
        'weights': weights.tolist(),
        'mse': mse,
        'prop_columns': prop_cols,
        'target_profile': target.tolist(),
        'progress': progress
    }
