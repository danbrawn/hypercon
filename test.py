from app import create_app, db, bcrypt
from app.models import User

app = create_app()
with app.app_context():
    admin = User(username="admin", role="admin")
    admin.set_password("admin")
    db.session.add(admin)
    db.session.commit()