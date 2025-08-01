from flask import Blueprint, request, render_template, flash, redirect, url_for, session
import pandas as pd
from sqlalchemy import MetaData, Table, select, text
from . import db
from flask_login import current_user,login_required

bp = Blueprint("materials", __name__)

def get_materials_table():
    # Избираме схема: операторите – от session, админ – main
    sch = session.get("schema") if current_user.role == "operator" else "main"
    meta = MetaData(schema=sch)
    return Table("materials_grit", meta, autoload_with=db.engine)

@bp.route("/materials")
@login_required
def page_materials():
    # вече сме сигурни, че current_user има атрибут role
    sch = session.get("schema") if current_user.role == "operator" else "main"
    tbl = Table(f"materials_grit", MetaData(), schema=sch, autoload_with=db.engine)
    #tbl = get_materials_table()
    # Покажи коя схема и коя таблица ползваме
    current_schema = tbl.schema or "public"
    table_name     = tbl.name

    # Четем редовете
    rows = db.session.execute(tbl.select()).mappings().all()

    # Подреждаме колоните: нестандартни + числови по нарастващо
    cols   = list(tbl.columns.keys())
    nonnum = [c for c in cols if not c.isdigit()]
    num    = sorted([c for c in cols if c.isdigit()], key=lambda x: int(x))
    columns = nonnum + num

    return render_template(
        "materials.html",
        schema=current_schema,
        table_name=table_name,
        columns=columns,
        rows=rows
    )

@bp.route("/materials/import", methods=["POST"])
def import_excel():
    f = request.files.get("file")
    if not f:
        flash("No file selected.", "danger")
        return redirect(url_for("materials.page_materials"))

    try:
        df = pd.read_excel(f)
        df.columns = df.columns.map(str)
        # Treat empty cells or whitespace as missing values
        df = df.replace(r'^\s*$', pd.NA, regex=True)
    except Exception as e:
        flash(f"Read error: {e}", "danger")
        return redirect(url_for("materials.page_materials"))

    tbl = get_materials_table()
    existing = set(tbl.columns.keys())

    # Добавяме нови колони, ако ги няма
    for col in df.columns:
        if col not in existing:
            ddl = text(
                f'ALTER TABLE "{tbl.schema}"."{tbl.name}" '
                f'ADD COLUMN "{col}" DOUBLE PRECISION'
            )
            db.session.execute(ddl)
    db.session.commit()

    # Презареждаме meta, за да хванем новите колони
    tbl = get_materials_table()
    cols = list(tbl.columns.keys())
    keycol = "material_name" if "material_name" in cols else cols[0]

    next_id = None
    if "id" in cols:
        from sqlalchemy import func

        next_id = (
            db.session.execute(select(func.max(tbl.c.id))).scalar() or 0
        ) + 1

    # Upsert логика
    for _, row in df.iterrows():
        data = {
            c: row[c]
            for c in df.columns
            if c in cols and pd.notna(row[c])
        }

        for opt in ("density", "strength", "spg", "kwa"):
            if opt in df.columns and pd.notna(row.get(opt)):
                data[opt] = row[opt]

        if "user_id" in cols:
            data["user_id"] = getattr(current_user, "id", None)

        key = data.get(keycol)
        if key is None:
            continue

        stmt = select(tbl).where(tbl.c[keycol] == key)
        if "user_id" in cols:
            stmt = stmt.where(tbl.c.user_id == current_user.id)
        exists = db.session.execute(stmt).first()

        if exists:
            upd = tbl.update().where(tbl.c[keycol] == key)
            if "user_id" in cols:
                upd = upd.where(tbl.c.user_id == current_user.id)
            upd = upd.values(**{k: v for k, v in data.items() if k != keycol})
            db.session.execute(upd)
        else:
            if "id" in cols and "id" not in data and next_id is not None:
                data["id"] = next_id
                next_id += 1
            db.session.execute(tbl.insert().values(**data))

    db.session.commit()
    flash("Import successful.", "success")
    return redirect(url_for("materials.page_materials"))


@bp.route("/materials/delete", methods=["POST"])
@login_required
def delete_rows():
    ids = request.form.getlist("row_id")
    if ids:
        tbl = get_materials_table()
        db.session.execute(tbl.delete().where(tbl.c.id.in_(map(int, ids))))
        db.session.commit()
        flash("Rows deleted.", "success")
    else:
        flash("No rows selected.", "warning")
    return redirect(url_for("materials.page_materials"))
