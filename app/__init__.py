from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from .config import DB_URI

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"]    = DB_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "change_me"

    db.init_app(app)

    # автоматично създава само ако НЕ съществува (но при reflection не е нужен)
    with app.app_context():
        db.create_all()

    from .routes_materials import bp as materials_bp
    app.register_blueprint(materials_bp)

    return app
