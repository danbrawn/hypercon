# app/__init__.py

# ◉ Monkey-patch for Flask-WTF & new Werkzeug
import urllib.parse, werkzeug.urls
werkzeug.urls.url_encode = lambda q, charset='utf-8', separator='&': urllib.parse.urlencode(q, doseq=True)

import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, redirect, url_for, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_bcrypt import Bcrypt
from flask_wtf import CSRFProtect
from sqlalchemy import text
from .config import DB_URI
from .middleware import RequestLoggerMiddleware

# ── Extensions ───────────────────────────────────────────────────────────────
db            = SQLAlchemy()
login_manager = LoginManager()
bcrypt        = Bcrypt()
csrf          = CSRFProtect()

def create_app():
    app = Flask(__name__, static_folder='static', static_url_path='')
    # — Load base config & override
    app.config.update(
        SQLALCHEMY_DATABASE_URI        = DB_URI,
        SQLALCHEMY_TRACK_MODIFICATIONS = False,
        SECRET_KEY                     = os.environ.get("SECRET_KEY", "change_me_for_prod"),
        WTF_CSRF_TIME_LIMIT            = None,
        SEND_FILE_MAX_AGE_DEFAULT      = 0  # for development
    )
    # Note: database credentials are loaded via ``app.config`` from
    # ``app/config.py``. The ``config.ini`` file is INI format and cannot be
    # executed by ``from_pyfile``; attempting to do so results in a
    # ``NameError`` at startup. Any further Flask configuration should be
    # performed via environment variables or ``config.py``.

    # ── Logging setup ──────────────────────────────────────────────────────────
    if app.debug:
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger("werkzeug").setLevel(logging.INFO)
        logging.getLogger("access").setLevel(logging.INFO)
    else:
        os.makedirs("logs", exist_ok=True)
        handler = RotatingFileHandler(
            "logs/hypercon.log", maxBytes=10*1024*1024, backupCount=5
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
        ))
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info("Hypercon startup")

    # ── Initialize extensions ──────────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view            = "auth.login"
    login_manager.login_message         = "Please log in to continue."
    login_manager.login_message_category= "warning"
    bcrypt.init_app(app)
    csrf.init_app(app)

    @app.after_request
    def add_security_headers(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"
        return response

    @login_manager.user_loader
    def load_user(user_id):
        # import here to avoid top‑level circular import
        from .models import User
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_user():
        return dict(current_user=current_user)

    @app.before_request
    def set_search_path():
        sch = session.get("schema")
        if sch:
            db.session.execute(text(f"SET search_path TO {sch}, main"))
        else:
            db.session.execute(text("SET search_path TO main"))

    @app.errorhandler(Exception)
    def handle_exception(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException) and e.code < 500:
            return e
        app.logger.error("Unhandled Exception", exc_info=e)
        return e

    # ── Create tables & load metadata ─────────────────────────────────────────
    with app.app_context():
        db.session.execute(text("SET search_path TO main"))
        db.create_all()

    # ── Blueprint registration ────────────────────────────────────────────────
    from .routes_auth      import bp as auth_bp
    from .routes_admin     import bp as admin_bp
    from .routes_materials import bp as materials_bp
    from .routes_optimize  import bp as optimize_bp
    from .routes_results   import bp as results_bp

    app.register_blueprint(auth_bp,      url_prefix="/auth")
    app.register_blueprint(admin_bp,     url_prefix="/admin")
    app.register_blueprint(materials_bp)             # no prefix
    app.register_blueprint(optimize_bp,   url_prefix="/optimize")
    app.register_blueprint(results_bp)               # /results

    # ── Root and favicon ─────────────────────────────────────────────────────
    @app.route("/")
    def index():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        return redirect(url_for("materials.page_materials"))

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(
            os.path.join(app.root_path, 'static'),
            'favicon.ico',
            mimetype='image/vnd.microsoft.icon'
        )

    # ── Wrap in request‑logging middleware ────────────────────────────────────
    return RequestLoggerMiddleware(app)
