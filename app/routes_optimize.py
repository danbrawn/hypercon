
from flask import Blueprint, render_template, jsonify, request, session, current_app
from flask_login import login_required, current_user
from sqlalchemy import select
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from . import db
from .optimize import run_full_optimization, _get_materials_table
from .models import ResultsRecipe

bp = Blueprint('optimize_bp', __name__)
_executor = ThreadPoolExecutor(max_workers=1)

@bp.route('', methods=['GET'])
@login_required
def page():
    schema = session.get('schema', 'main')
    tbl = _get_materials_table(schema)
    table_name = tbl.name
    stmt = select(*[c.label(c.name) for c in tbl.c])
    # Fetch rows as mappings so column names can be accessed directly
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

    try:
        materials_raw = request.form.get('materials')
        constraints_raw = request.form.get('constraints')

        material_ids = json.loads(materials_raw) if materials_raw else None
        constr = json.loads(constraints_raw) if constraints_raw else None

        if not material_ids:
            return jsonify(error="No materials selected"), 400

        schema = session.get('schema', 'main')
        user_id = current_user.id

        def task():
            with current_app.app_context():
                try:
                    result = run_full_optimization(
                        schema=schema,
                        material_ids=material_ids,
                        constraints=[(int(c['id']), c['op'], float(c['val'])) for c in constr]
                        if constr
                        else None,
                        user_id=user_id,
                    )
                    if not result:
                        raise RuntimeError("Optimization failed")

                    materials = [
                        {"name": name, "percent": float(weight)}
                        for name, weight in zip(result["material_names"], result["weights"])
                    ]
                    db.session.add(ResultsRecipe(mse=result["best_mse"], materials=materials))
                    db.session.commit()
                    return result
                except Exception:
                    db.session.rollback()
                    raise

        future = _executor.submit(task)
        try:
            result = future.result(timeout=25)
            return jsonify(result)
        except FuturesTimeout:
            return (
                jsonify(
                    error="Optimization is taking longer than expected. "
                    "Results will appear on the Results page when ready."
                ),
                202,
            )
    except Exception as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 500
