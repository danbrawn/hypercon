from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required, current_user
from sqlalchemy import MetaData, Table, select

from .optimize import _is_number

from .tasks import optimize_task
from kombu.exceptions import OperationalError
from . import db
from celery.result import AsyncResult

bp = Blueprint('optimize', __name__, url_prefix='/optimize')


def _get_materials_table():
    sch = session.get("schema") if current_user.role == "operator" else "main"
    meta = MetaData(schema=sch)
    return Table("materials_grit", meta, autoload_with=db.engine)


@bp.route('', methods=['GET'])
@login_required
def page_optimize():
    """Render the optimization page with material data and numeric columns."""
    tbl = _get_materials_table()
    rows = db.session.execute(select(tbl)).mappings().all()
    numeric_cols = [c.key for c in tbl.columns if _is_number(c.key)]
    numeric_cols.sort(key=lambda x: float(x))
    return render_template(
        'optimize.html',
        materials=rows,
        prop_columns=numeric_cols
    )


@bp.route('/start', methods=['POST'])
@login_required
def start():
    params = request.json
    try:
        job = optimize_task.apply_async(args=[params])
    except OperationalError:
        # Fallback when the Celery broker/backend is unreachable
        result = optimize_task.run(params)
        return jsonify(status='SUCCESS', result=result), 200
    return jsonify(job_id=job.id), 202


@bp.route('/status/<job_id>', methods=['GET'])
@login_required
def status(job_id):
    job = AsyncResult(job_id, app=optimize_task.app)
    resp = {'status': job.status}
    if job.ready():
        resp['result'] = job.result
    return jsonify(resp)
