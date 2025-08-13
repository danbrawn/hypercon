"""Routes for launching and monitoring optimization jobs in a background thread."""

from flask import Blueprint, render_template, jsonify, request, session, current_app
from flask_login import login_required, current_user
from sqlalchemy import select
from concurrent.futures import ThreadPoolExecutor
import time
import threading

from . import db
from .optimize import run_full_optimization, _get_materials_table
from .models import ResultsRecipe

bp = Blueprint('optimize_bp', __name__)
_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[int, dict] = {}


# Single-worker executor keeps CPU usage predictable and ensures only one
# optimization runs at a time per process.
_executor = ThreadPoolExecutor(max_workers=1)

# In-memory registry of active jobs keyed by user id. Each job stores the
# future, a stop event, progress fraction, best-so-far result, and start time.
_jobs: dict[int, dict] = {}


# Single-worker executor keeps CPU usage predictable and ensures only one
# optimization runs at a time per process.
_executor = ThreadPoolExecutor(max_workers=1)

# In-memory registry of active jobs keyed by user id. Each job stores the
# future, a stop event, progress fraction, best-so-far result, and start time.
_jobs: dict[int, dict] = {}


# Single-worker executor keeps CPU usage predictable and ensures only one
# optimization runs at a time per process.
_executor = ThreadPoolExecutor(max_workers=1)

# In-memory registry of active jobs keyed by user id. Each job stores the
# future, a stop event, progress fraction, best-so-far result, and start time.
_jobs: dict[int, dict] = {}


# Single-worker executor keeps CPU usage predictable and ensures only one
# optimization runs at a time per process.
_executor = ThreadPoolExecutor(max_workers=1)

# In-memory registry of active jobs keyed by user id. Each job stores the
# future, a stop event, progress fraction, best-so-far result, and start time.
_jobs: dict[int, dict] = {}


@bp.route('', methods=['GET'])
@login_required
def page():
    schema = session.get('schema', 'main')
    tbl = _get_materials_table(schema)
    table_name = tbl.name
    stmt = select(*[c.label(c.name) for c in tbl.c])
    # Fetch rows as mappings so column names can be accessed directly
    rows = db.session.execute(stmt).mappings().all()
    cols = list(tbl.columns.keys())
    nonnum = [c for c in cols if not c.isdigit()]
    num = sorted([c for c in cols if c.isdigit()], key=lambda x: int(x))
    columns = ['use'] + nonnum + num
    materials = [{'id': r['id'], 'name': r['material_name']} for r in rows]
    return render_template(
        'optimize.html',
        schema=schema,
        table_name=table_name,
        columns=columns,
        rows=rows,
        materials=materials,
    )


@bp.route('/run', methods=['POST'])
@login_required
def run():
    """Kick off an optimization in a worker thread and return immediately."""
    import json

    try:
        materials_raw = request.form.get('materials')
        constraints_raw = request.form.get('constraints')

        material_ids = json.loads(materials_raw) if materials_raw else None
        constr = json.loads(constraints_raw) if constraints_raw else None

        if not material_ids:
            return jsonify(error="No materials selected"), 400

        user_id = current_user.id
        if user_id in _jobs and not _jobs[user_id]['future'].done():
            return jsonify(error="Optimization already running"), 409

        schema = session.get('schema', 'main')
        app = current_app._get_current_object()

        job = {
            'start': time.time(),
            'stop': threading.Event(),
            'best': None,
            'progress': 0.0,
        }
        _jobs[user_id] = job

        def progress_cb(update):
            if 'best' in update:
                job['best'] = update['best']
            if 'progress' in update:
                job['progress'] = update['progress']

        def task():
            with app.app_context():
                try:
                    result = run_full_optimization(
                        schema=schema,
                        material_ids=material_ids,
                        constraints=[(int(c['id']), c['op'], float(c['val'])) for c in constr]
                        if constr
                        else None,
                        user_id=user_id,
                        progress_cb=progress_cb,
                        stop_event=job['stop'],
                    )
                    if not result:
                        raise RuntimeError("Optimization failed")

                    materials = [
                        {"name": name, "percent": float(weight)}
                        for name, weight in zip(result["material_names"], result["weights"])
                    ]
                    db.session.add(ResultsRecipe(mse=result["best_mse"], materials=materials))
                    db.session.commit()
                    return result
                except Exception:
                    db.session.rollback()
                    raise

        future = _executor.submit(task)
        job['future'] = future

        def done_cb(fut):
            try:
                job['result'] = fut.result()
            except Exception:
                job['result'] = None

        future.add_done_callback(done_cb)

        return jsonify(status="running"), 202
    except Exception as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 500


@bp.route('/status', methods=['GET'])
@login_required
def status():
    """Report progress for the current user's running job if any."""
    user_id = current_user.id
    job = _jobs.get(user_id)
    if not job:
        return jsonify(status="idle")

    elapsed = time.time() - job['start']
    fut = job.get('future')
    if fut and fut.done():
        result = job.get('result') or job.get('best')
        _jobs.pop(user_id, None)
        if result:
            return jsonify(status="done", elapsed=elapsed, progress=1.0, result=result)
        return jsonify(status="error", elapsed=elapsed, progress=job.get('progress', 0.0))

    return jsonify(status="running", elapsed=elapsed, progress=job.get('progress', 0.0), best=job.get('best'))


@bp.route('/stop', methods=['POST'])
@login_required
def stop():
    """Signal the background optimization to halt."""
    user_id = current_user.id
    job = _jobs.get(user_id)
    if not job:
        return jsonify(error="No running optimization"), 400
    job['stop'].set()
    return jsonify(status="stopping", result=job.get('best'))

