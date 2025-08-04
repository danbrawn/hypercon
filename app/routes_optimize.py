
from flask import Blueprint, render_template, jsonify, request, session
from flask_login import login_required
from threading import Thread
from uuid import uuid4

from . import db
from .optimize import run_full_optimization, _get_materials_table
from .models import ResultsRecipe

bp = Blueprint('optimize_bp', __name__)

# simple in-memory job store
_jobs: dict[str, dict] = {}

@bp.route('', methods=['GET'])
@login_required
def page():
    schema = session.get('schema', 'main')
    tbl = _get_materials_table(schema)
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
    schema = request.form.get('schema') or session.get('schema')

    material_ids = json.loads(materials_raw) if materials_raw else None
    constr = json.loads(constraints_raw) if constraints_raw else None

    if not material_ids:
        return jsonify(error="No materials selected"), 400

    job_id = uuid4().hex
    # start with a dummy total > 0 so the UI knows the job is in progress
    progress = {"total": 1, "done": 0}
    _jobs[job_id] = {"progress": progress, "result": None, "error": None}

    def worker():
        try:
            result = run_full_optimization(
                material_ids=material_ids,
                constraints=[(int(c['id']), c['op'], float(c['val'])) for c in constr] if constr else None,
            )
            _jobs[job_id]["result"] = result
        except Exception as exc:
            _jobs[job_id]["error"] = str(exc)
        finally:
            progress["done"] = progress["total"]

    Thread(target=worker, daemon=True).start()
    return jsonify(job_id=job_id)


@bp.route('/progress')
@login_required
def progress():
    job_id = request.args.get('job_id')
    job = _jobs.get(job_id)
    if not job:
        return jsonify(error="Unknown job"), 404
    prog = job["progress"]
    data = {"total": prog["total"], "done": prog["done"]}
    if job["error"]:
        data["error"] = job["error"]
    if job["result"] is not None:
        data["result"] = job["result"]
    return jsonify(data)
