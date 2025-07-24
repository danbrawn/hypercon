from celery import Celery
from .optimize import load_data, optimize_combo

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
    try:
        ids, values, target, prop_cols = load_data(params)
    except ValueError as exc:
        return {'error': str(exc)}

    out = optimize_combo(values, target)
    if not out:
        return {'error': 'Optimization failed'}
    mse, weights = out
    return {
        'material_ids': ids,
        'weights': weights.tolist(),
        'mse': mse,
        'prop_columns': prop_cols,
        'target_profile': target.tolist()
    }
