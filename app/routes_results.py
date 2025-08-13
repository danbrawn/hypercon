from flask import Blueprint, render_template, session
from flask_login import login_required
from sqlalchemy import select
import json

from . import db
from .optimize import _get_results_table

bp = Blueprint('results', __name__)

@bp.route('/results')
@login_required
def page():
    schema = session.get('schema', 'main')
    tbl = _get_results_table(schema)
    stmt = select(tbl).order_by(tbl.c.dateref.desc())
    rows = db.session.execute(stmt).mappings().all()
    results = []
    for r in rows:
        mats = r["materials"]
        # Materials may be stored as a JSON string; decode when necessary.
        if isinstance(mats, str):
            try:
                mats = json.loads(mats)
            except json.JSONDecodeError:
                mats = []
        results.append(
            {
                "id": r["id"],
                "dateref": r["dateref"],
                "mse": r["mse"],
                "materials": mats,
                "names": ", ".join(m["name"] for m in mats),
            }
        )
    return render_template('results.html', results=results)
