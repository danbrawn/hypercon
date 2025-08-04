from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import select
import json

from . import db
from .optimize import _get_results_table

bp = Blueprint('results_bp', __name__)

@bp.route('', methods=['GET'])
@login_required
def page():
    tbl = _get_results_table()
    rows = db.session.execute(select(tbl).order_by(tbl.c.DateRef.desc())).mappings().all()
    results = []
    for r in rows:
        mats = json.loads(r['materials']) if r['materials'] else {}
        results.append({
            'id': r['ID'] if 'ID' in r else r.get('id'),
            'dateref': r['DateRef'] if 'DateRef' in r else r.get('dateref'),
            'mse': r['mse'],
            'materials': mats,
            'names': ', '.join(mats.keys()),
        })
    return render_template('results.html', results=results)
