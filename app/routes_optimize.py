from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from threading import Thread
from uuid import uuid4

from . import db
from .optimize import run_full_optimization, _get_materials_table

bp = Blueprint('optimize_bp', __name__)

# simple in-memory job store
_jobs: dict[str, dict] = {}

@bp.route('', methods=['GET'])
@login_required
def page():
    tbl = _get_materials_table()
    schema = tbl.schema or 'public'
    table_name = tbl.name
    rows = db.session.execute(tbl.select()).mappings().all()
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
    import json

    materials_raw = request.form.get('materials')
    constraints_raw = request.form.get('constraints')
    schema = request.form.get('schema') or None

    material_ids = json.loads(materials_raw) if materials_raw else None
    constr = json.loads(constraints_raw) if constraints_raw else None

    job_id = str(uuid4())
    progress = {"total": 0, "done": 0}
    _jobs[job_id] = {"progress": progress, "result": None, "error": None}

    user_id = current_user.id if hasattr(current_user, 'id') else None

    def worker():
        with current_app.app_context():
            try:
                res = run_full_optimization(
                    schema=schema,
                    material_ids=material_ids,
                    constraints=[(int(c['id']), c['op'], float(c['val'])) for c in constr] if constr else None,
                    progress=progress,
                    user_id=user_id,
                )
                _jobs[job_id]["result"] = res
            except Exception as exc:
                _jobs[job_id]["error"] = str(exc)
            finally:
                progress["done"] = progress.get("total", 0)

    Thread(target=worker, daemon=True).start()

    return jsonify(job_id=job_id)


@bp.route('/progress/<job_id>', methods=['GET'])
@login_required
def progress(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return jsonify(error='invalid job'), 404
    data = dict(job['progress'])
    if job['result'] is not None:
        data['result'] = job['result']
    if job['error'] is not None:
        data['error'] = job['error']
    return jsonify(data)
