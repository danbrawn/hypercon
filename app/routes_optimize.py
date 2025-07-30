from flask import Blueprint, render_template, jsonify
from flask_login import login_required

from .optimize import run_full_optimization

bp = Blueprint('optimize_bp', __name__)

@bp.route('', methods=['GET'])
@login_required
def page():
    return render_template('optimize.html')

@bp.route('/run', methods=['POST'])
@login_required
def run():
    try:
        result = run_full_optimization()
    except Exception as exc:
        return jsonify(error=str(exc)), 400
    if result is None:
        return jsonify(error='Optimization failed'), 400
    return jsonify(result)
