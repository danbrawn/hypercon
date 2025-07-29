# app/routes_optimize.py
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from .optimize_jobs import start_job, jobs
from .optimize import _is_number, _get_materials_table
from . import db

bp = Blueprint('optimize_bp', __name__, url_prefix='/optimize')

@bp.route('', methods=['GET'])
@login_required
def optimize_page():
    # reflect numeric columns from the current user's materials table
    mat = _get_materials_table()
    prop_columns = [c.name for c in mat.columns if _is_number(c.name)]

    # load the user’s full material set just for the form
    rows = db.session.execute(
        mat.select().where(mat.c.user_id == current_user.id)
    ).mappings().all()
    return render_template('optimize.html',
                           materials=rows,
                           prop_columns=prop_columns)

@bp.route('/start', methods=['POST'])
@login_required
def start():
    params = request.json or {}
    params.setdefault('max_combo', 5)
    job_id = start_job(params)
    return jsonify(job_id=job_id), 202

@bp.route('/status/<job_id>', methods=['GET'])
@login_required
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify(error='Unknown job_id'), 404
    resp = {
        'status':   job['status'],
        'progress': job['progress'],
        'best_mse': job['best_mse']
    }
    if job['status'] == 'SUCCESS':
        resp['result'] = job['result']
    return jsonify(resp)
