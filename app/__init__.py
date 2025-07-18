# app/__init__.py

# ◉ Monkey-patch за Flask-WTF & нов Werkzeug
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

# ── Extensions ────────────────────────────────────────────────────────────────
db            = SQLAlchemy()
login_manager = LoginManager()
bcrypt        = Bcrypt()
csrf          = CSRFProtect()

# ── Middleware за логване на всеки HTTP request ───────────────────────────────
class RequestLoggerMiddleware:
    def __init__(self, app):
        self.app    = app
        self.logger = logging.getLogger("access")

    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD")
        path   = environ.get("PATH_INFO")
        self.logger.info(f"{method} {path}")
        return self.app(environ, start_response)


def create_app():
    app = Flask(__name__)
    app.config.update(static_folder='static', static_url_path='',
        SQLALCHEMY_DATABASE_URI        = DB_URI,
        SQLALCHEMY_TRACK_MODIFICATIONS = False,
        SECRET_KEY                     = os.environ.get("SECRET_KEY", "change_me_for_prod"),
        WTF_CSRF_TIME_LIMIT            = None,
        SEND_FILE_MAX_AGE_DEFAULT = 0  # за development
    )

    # ── Настройка на логване ─────────────────────────────────────────────────
    if app.debug:
        # в Dev Mode логваме DEBUG и HTTP requests
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger("werkzeug").setLevel(logging.INFO)
        logging.getLogger("access").setLevel(logging.INFO)
    else:
        # в Prod Mode записваме в ротационен файл
        os.makedirs("logs", exist_ok=True)
        handler = RotatingFileHandler(
            "logs/hypercon.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
        ))
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info("Hypercon startup")

    # ── Инициализиране на extensions ─────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Моля, влезте, за да продължите."
    login_manager.login_message_category = "warning"
    bcrypt.init_app(app)
    csrf.init_app(app)

    @app.after_request
    def add_security_headers(response):
        # Забраняваме кеширане:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    # ── Регистрация на user_loader ──────────────────────────────────────────
    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(int(user_id))

    login_manager.login_view    = "auth.login"
    login_manager.login_message = "Моля, влезте, за да продължите."

    # ── Достъп до current_user в Jinja шаблони ───────────────────────────────
    @app.context_processor
    def inject_user():
        return dict(current_user=current_user)

    # ── Задаване на search_path според session['schema'] ─────────────────────
    @app.before_request
    def set_search_path():
        sch = session.get("schema")
        if sch:
            db.session.execute(text(f"SET search_path TO {sch}, main"))
        else:
            db.session.execute(text("SET search_path TO main"))

    # ── Глобален error handler за логване на неконтролирани изключения ───────
    @app.errorhandler(Exception)
    def handle_exception(e):
        app.logger.error("Unhandled Exception", exc_info=e)
        raise

    # ── Създаване на таблиците при стартиране (MVP shortcut) ─────────────────
    with app.app_context():
        db.create_all()

    # ── Регистрация на Blueprints ────────────────────────────────────────────
    from .routes_auth      import bp as auth_bp
    from .routes_admin     import bp as admin_bp
    from .routes_materials import bp as materials_bp

    app.register_blueprint(auth_bp,      url_prefix="/auth")
    app.register_blueprint(admin_bp,     url_prefix="/admin")
    app.register_blueprint(materials_bp)  # без префикс

    # ── Root redirect към login или /materials ───────────────────────────────
    @app.route("/")
    def index():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        return redirect(url_for("materials.page_materials"))

    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico',
                                   mimetype='image/vnd.microsoft.icon')

    # ── Обгръщаме с middleware за лог на заявките ───────────────────────────
    return RequestLoggerMiddleware(app)
