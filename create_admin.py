"""Utility script to ensure an admin user and default client exist."""

from app import create_app, db
from app.models import Client, User


def main() -> None:
    wrapped_app = create_app()
    app = getattr(wrapped_app, "app", wrapped_app)
    with app.app_context():
        # ensure a default client for operators
        if not Client.query.filter_by(name="Default").first():
            client = Client(name="Default", schema_name="main")
            db.session.add(client)
            db.session.commit()
            print("Default client created.")
        else:
            print("Default client already exists.")

        if User.query.filter_by(username="admin").first():
            print("Admin already exists.")
        else:
            admin = User(username="admin", role="admin")
            admin.set_password("admin")
            db.session.add(admin)
            db.session.commit()
            print("Admin created successfully.")


if __name__ == "__main__":
    main()

