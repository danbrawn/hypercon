
from flask import Blueprint, render_template, jsonify, request, session
from flask_login import login_required, current_user
from sqlalchemy import select
from sqlalchemy.sql.expression import LABEL_STYLE_NONE

from . import db
from .optimize import run_full_optimization, _get_materials_table
from .models import ResultsRecipe

bp = Blueprint('optimize_bp', __name__)

@bp.route('', methods=['GET'])
@login_required
def page():
    schema = session.get('schema', 'main')
    tbl = _get_materials_table(schema)
    table_name = tbl.name
    stmt = select(tbl).set_label_style(LABEL_STYLE_NONE)
    rows = db.session.execute(stmt).mappings().all()
    cols = list(tbl.columns.keys())
    nonnum = [c for c in cols if not c.isdigit()]
    num = sorted([c for c in cols if c.isdigit()], key=lambda x: int(x))
    columns = ['use'] + nonnum + num
    materials = [{'id': r['id'], 'name': r['material_name']} for r in rows]
    return render_template(
        'optimize.html',
        schema=schema,
        table_name=table_name,
        columns=columns,
        rows=rows,
        materials=materials,
    )

@bp.route('/run', methods=['POST'])
@login_required
def run():
    import json

    materials_raw = request.form.get('materials')
    constraints_raw = request.form.get('constraints')
    schema = request.form.get('schema') or session.get('schema')

    material_ids = json.loads(materials_raw) if materials_raw else None
    constr = json.loads(constraints_raw) if constraints_raw else None

    if not material_ids:
        return jsonify(error="No materials selected"), 400

    schema = session.get('schema', 'main')
    user_id = current_user.id

    try:
        result = run_full_optimization(
            schema=schema,
            material_ids=material_ids,
            constraints=[(int(c['id']), c['op'], float(c['val'])) for c in constr] if constr else None,
            user_id=user_id,
        )
    except Exception as exc:
        return jsonify(error=str(exc)), 500

    if not result:
        return jsonify(error="Optimization failed"), 500

    materials = [
        {"name": name, "percent": float(weight)}
        for name, weight in zip(result["material_names"], result["weights"])
    ]
    db.session.add(ResultsRecipe(mse=result["best_mse"], materials=materials))
    db.session.commit()

    return jsonify(result)
