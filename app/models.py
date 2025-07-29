from . import db
from flask_login import UserMixin

class Client(db.Model):
    __tablename__ = "clients"
    __table_args__ = {'schema': 'main'}

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String,  unique=True, nullable=False)
    schema_name = db.Column(db.String,  unique=True, nullable=False)

class User(db.Model, UserMixin):
    __tablename__ = "users"
    __table_args__ = {'schema': 'main'}

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.Text,      nullable=False)
    role          = db.Column(db.String(20), nullable=False, default="operator")
    client_id     = db.Column(db.Integer, db.ForeignKey("main.clients.id"))

    client        = db.relationship("Client", backref="users")

    def set_password(self, pw):
        from flask_bcrypt import generate_password_hash
        self.password_hash = generate_password_hash(pw).decode()

    def check_password(self, pw):
        from flask_bcrypt import check_password_hash
        return check_password_hash(self.password_hash, pw)