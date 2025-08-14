from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from . import db, bcrypt
from .models import User, Client

bp = Blueprint("auth", __name__)

@bp.route("/login", methods=["GET","POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("materials.page_materials"))

    if request.method == "POST":
        uname = request.form["username"]
        pw    = request.form["password"]
        user  = User.query.filter_by(username=uname).first()
        if user and user.check_password(pw):
            login_user(user)
            # set schema in session for operator
            if user.role == "operator" and user.client:
                session["schema"] = user.client.schema_name
            else:
                session.pop("schema", None)
            return redirect(url_for("materials.page_materials"))
        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("schema", None)
    flash("Logged out successfully.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/tetris")
def tetris():
    if current_user.is_authenticated:
        render_template("tetris.html")
    else:
        return redirect(url_for("auth.login"))

