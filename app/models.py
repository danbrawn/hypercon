from . import db
from .config import MATERIALS_TABLE
from . import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class Material(db.Model):
    __tablename__ = MATERIALS_TABLE

    id    = db.Column(db.Integer, primary_key=True)
    name  = db.Column(db.String(120), unique=True, nullable=False)
    price = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f"<Material {self.id}: {self.name}, {self.price}>"


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id             = db.Column(db.Integer,   primary_key=True)
    username       = db.Column(db.String(80), unique=True, nullable=False)
    password_hash  = db.Column(db.String(128), nullable=False)
    role           = db.Column(db.String(20), nullable=False, default="operator")
    # helper-и за паролата
    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)
    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)