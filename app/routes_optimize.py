from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from .models import MaterialGrit
from .optimize_jobs import start_job, jobs

bp = Blueprint('optimize_bp', __name__, url_prefix='/optimize')

@bp.route('', methods=['GET'])
@login_required
def optimize_page():
    # Load all materials for this user
    mats = MaterialGrit.query.filter_by(user_id=current_user.id).all()
    # Get numeric property columns
    from sqlalchemy import inspect
    mapper = inspect(MaterialGrit)
    prop_columns = [c.key for c in mapper.attrs if _is_number(c.key)]
    return render_template(
        'optimize.html',
        materials=mats,
        prop_columns=prop_columns
    )

def _is_number(x):
    try: float(x); return True
    except: return False

@bp.route('/start', methods=['POST'])
@login_required
def start_optimize():
    params = request.json
    # augment with defaults
    params.setdefault('max_combo', 5)
    job_id = start_job(params)
    return jsonify({'job_id': job_id}), 202

@bp.route('/status/<job_id>', methods=['GET'])
@login_required
def check_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Unknown job'}), 404
    resp = {
        'status':   job['status'],
        'progress': job['progress'],
        'best_mse': job['best_mse']
    }
    if job['status'] == 'SUCCESS':
        resp['result'] = job['result']
    return jsonify(resp)
