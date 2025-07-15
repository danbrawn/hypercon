from flask import Blueprint, request, render_template, flash, redirect, url_for, session
import pandas as pd
from sqlalchemy import MetaData, Table, select, text
from . import db
from flask_login import current_user

bp = Blueprint("materials", __name__)

def get_materials_table():
    # Избираме схема: операторите – от session, админ – main
    sch = session.get("schema") if current_user.role == "operator" else "main"
    meta = MetaData(schema=sch)
    return Table("materials_grit", meta, autoload_with=db.engine)

@bp.route("/materials")
def page_materials():
    tbl = get_materials_table()
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
        flash("Не е избран файл.", "danger")
        return redirect(url_for("materials.page_materials"))

    try:
        df = pd.read_excel(f)
        df.columns = df.columns.map(str)
    except Exception as e:
        flash(f"Грешка при четене: {e}", "danger")
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

    # Upsert логика
    for _, row in df.iterrows():
        data = {c: row[c] for c in df.columns if c in cols and pd.notna(row[c])}
        key = data.get(keycol)
        if key is None:
            continue

        exists = db.session.execute(
            select(tbl).where(tbl.c[keycol] == key)
        ).first()

        if exists:
            upd = tbl.update().where(tbl.c[keycol] == key).values(
                **{k: v for k, v in data.items() if k != keycol}
            )
            db.session.execute(upd)
        else:
            db.session.execute(tbl.insert().values(**data))

    db.session.commit()
    flash("Импортирано успешно.", "success")
    return redirect(url_for("materials.page_materials"))
