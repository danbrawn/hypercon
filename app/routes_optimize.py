from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required

from . import db
from .optimize import run_full_optimization, _get_materials_table, get_progress

bp = Blueprint('optimize_bp', __name__)

@bp.route('', methods=['GET'])
@login_required
def page():
    tbl = _get_materials_table()
    schema = tbl.schema or 'public'
    table_name = tbl.name
    rows = db.session.execute(tbl.select()).mappings().all()
    cols = list(tbl.columns.keys())
    nonnum = [c for c in cols if not c.isdigit()]
    num = sorted([c for c in cols if c.isdigit()], key=lambda x: int(x))
    columns = ['use'] + nonnum + num
    return render_template(
        'optimize.html',
        schema=schema,
        table_name=table_name,
        columns=columns,
        rows=rows,
    )

@bp.route('/run', methods=['POST'])
@login_required
def run():
    import json

    materials_raw = request.form.get('materials')
    constraints_raw = request.form.get('constraints')

    material_ids = json.loads(materials_raw) if materials_raw else None
    constr = json.loads(constraints_raw) if constraints_raw else None

    try:
        result = run_full_optimization(
            material_ids=material_ids,
            constraints=[(int(c['id']), c['op'], float(c['val'])) for c in constr] if constr else None,
        )
    except Exception as exc:
        return jsonify(error=str(exc)), 400
    if result is None:
        return jsonify(error='Optimization failed'), 400
    return jsonify(result)


@bp.route('/progress', methods=['GET'])
@login_required
def progress():
    return jsonify(get_progress())
