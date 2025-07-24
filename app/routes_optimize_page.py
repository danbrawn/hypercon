from flask import Blueprint, render_template
from flask_login import login_required

bp = Blueprint('optimize', __name__)

@bp.route('/optimize')
@login_required
def page_optimize():
    return render_template('optimize.html')
