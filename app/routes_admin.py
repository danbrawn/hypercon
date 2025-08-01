from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import db
from .models import Client, User
from .utils import admin_required


bp = Blueprint("admin", __name__)

@bp.route("/clients", methods=["GET","POST"])
@login_required
@admin_required
def manage_clients():
    if request.method == "POST":
        name   = request.form["name"].strip()
        schema = request.form["schema_name"].strip()
        db.session.add(Client(name=name, schema_name=schema))
        db.session.commit()
        flash(f"Client {name} created.", "success")
        return redirect(url_for("admin.manage_clients"))

    clients = Client.query.all()
    return render_template("admin/clients.html", clients=clients)

@bp.route("/users", methods=["GET","POST"])
@login_required
@admin_required
def manage_users():
    if request.method == "POST":
        uname     = request.form["username"].strip()
        pw        = request.form["password"].strip()
        role      = request.form["role"]
        client_id = request.form.get("client_id") or None

        user = User(username=uname, role=role, client_id=client_id)
        user.set_password(pw)
        db.session.add(user)
        db.session.commit()
        flash(f"User {uname} created.", "success")
        return redirect(url_for("admin.manage_users"))

    users   = User.query.all()
    clients = Client.query.all()
    return render_template("admin/users.html", users=users, clients=clients)
