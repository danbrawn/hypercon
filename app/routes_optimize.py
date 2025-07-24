from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required, current_user
from sqlalchemy import MetaData, Table, select

from .tasks import optimize_task
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
    tbl = _get_materials_table()
    rows = db.session.execute(select(tbl)).mappings().all()
    return render_template('optimize.html', materials=rows)


@bp.route('/start', methods=['POST'])
@login_required
def start():
    params = request.json
    job = optimize_task.apply_async(args=[params])
    return jsonify(job_id=job.id), 202


@bp.route('/status/<job_id>', methods=['GET'])
@login_required
def status(job_id):
    job = AsyncResult(job_id, app=optimize_task.app)
    resp = {'status': job.status}
    if job.ready():
        resp['result'] = job.result
    return jsonify(resp)
