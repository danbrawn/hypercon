from celery import Celery
from .optimize import run_optimization  # новият модул

celery = Celery(
    'hypercon',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1'
)

@celery.task(bind=True)
def optimize_task(self, params):
    # Можете да докладвате прогрес:)))
    # self.update_state(state='PROGRESS', meta={'percent': 50})
    return run_optimization(params)
