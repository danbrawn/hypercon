from flask import Blueprint, render_template
from flask_login import login_required
from .models import ResultsRecipe

bp = Blueprint('results', __name__)

@bp.route('/results')
@login_required
def page():
    rows = ResultsRecipe.query.order_by(ResultsRecipe.dateref.desc()).all()
    results = [
        {
            'id': r.id,
            'dateref': r.dateref,
            'mse': r.mse,
            'materials': r.materials,
            'names': ', '.join(m['name'] for m in r.materials)
        }
        for r in rows
    ]
    return render_template('results.html', results=results)
