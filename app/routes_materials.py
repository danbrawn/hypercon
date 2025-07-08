# app/routes_materials.py

from flask import Blueprint, request, redirect, url_for, flash, render_template
import pandas as pd
from sqlalchemy import MetaData, Table, text

from . import db
from .config import MATERIALS_TABLE, MATERIALS_SCHEMA

bp = Blueprint("materials", __name__)

def reflect_table():
    meta = MetaData(schema=MATERIALS_SCHEMA)
    return Table(
        MATERIALS_TABLE,
        meta,
        autoload_with=db.engine
    )

@bp.route("/materials")
def page_materials():
    tbl = reflect_table()
    rows = db.session.execute(tbl.select()).mappings().all()
    cols = list(tbl.columns.keys())
    nonnum = [c for c in cols if not c.isdigit()]
    num    = sorted([c for c in cols if c.isdigit()], key=int)
    columns = nonnum + num
    return render_template("materials.html", columns=columns, rows=rows)

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
        flash(f"Грешка при четене на Excel: {e}", "danger")
        return redirect(url_for("materials.page_materials"))

    tbl = reflect_table()
    existing = set(tbl.columns.keys())
    # добавяме липсващи колони
    for col in df.columns:
        if col not in existing:
            ddl = text(f'ALTER TABLE "{MATERIALS_SCHEMA}"."{MATERIALS_TABLE}" '
                       f'ADD COLUMN "{col}" DOUBLE PRECISION')
            db.session.execute(ddl)
    db.session.commit()

    # рефлектираме отново
    tbl = reflect_table()

    # определяме ключова колона
    cols = list(tbl.columns.keys())
    if "material_name" in cols:
        keycol = "material_name"
    else:
        pks = [c.name for c in tbl.primary_key.columns]
        keycol = pks[0] if pks else next((c for c in cols if not c.isdigit()), cols[0])

    # upsert
    for _, row in df.iterrows():
        data = {col: row[col] for col in df.columns if col in cols and pd.notna(row[col])}
        key = data.get(keycol)
        if key is None:
            continue
        sel = tbl.select().where(tbl.c[keycol] == key)
        if db.session.execute(sel).first():
            upd = tbl.update().where(tbl.c[keycol] == key).values(**{k:v for k,v in data.items() if k!=keycol})
            db.session.execute(upd)
        else:
            db.session.execute(tbl.insert().values(**data))
    db.session.commit()

    flash("Импортирано успешно.", "success")
    return redirect(url_for("materials.page_materials"))
