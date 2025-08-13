# Hypercon Optimization Web App

Hypercon is a Flask-based web application for exploring and optimizing material combinations. It calculates mix ratios that minimize mean squared error (MSE) against a target profile and displays results in real time.

## Project structure

- **run.py** – production entry point using Waitress to serve the app.
- **app/** – main application package
  - **__init__.py** – application factory and extension initialization
  - **config.py** – configuration settings loaded from `config.ini`
  - **models.py** – SQLAlchemy models
  - **routes_*.py** – Flask blueprints for authentication, materials management, optimization workflow, admin tools, and results viewing
  - **optimize.py** – optimization helpers and threading utilities
  - **static/** – frontend assets (JavaScript, CSS)
  - **templates/** – Jinja2 templates for HTML pages
- **create_admin.py** – command-line tool that seeds the database with a "Default" client and an initial admin user (`admin`/`admin`)
- **optimize_db.py** – runs a full optimization using the current materials in the database and prints the best mix
- **optimize_recipe_db.py** – brute-force optimizer that loads material profiles from the database and refines the best combination using multi-start SLSQP
- **setup-service.ps1** – PowerShell helper for installing the app as a Windows service
- **requirements.txt** – Python package dependencies

## Utility scripts

Run these helpers from the repository root:

- Seed the database with a default client and admin user:

  ```bash
  python create_admin.py
  ```

- Perform a one-off optimization using the materials stored in the database and print the best mix:

  ```bash
  python optimize_db.py
  ```

- Explore and optimize combinations locally with a brute-force search and SLSQP refinement:

  ```bash
  python optimize_recipe_db.py
  ```

Each script uses the same configuration and database settings as the web application.

## Technology

- [Flask](https://flask.palletsprojects.com/) web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) ORM for database access
- [Waitress](https://docs.pylonsproject.org/projects/waitress/) WSGI server
- [pytest](https://docs.pytest.org/) for automated tests

## Optimization threading

Lengthy searches run in a background thread so the web request can return immediately and
avoid gateway timeouts. Each user gets a single queued job managed by a
`ThreadPoolExecutor`. Progress updates and the best interim result are stored in
memory and exposed through `/status` and `/stop` endpoints, allowing the frontend to
poll for updates and optionally cancel a run while preserving the best mix found so far.

## Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run tests:
   ```bash
   python -m pytest
   ```
3. Start the development server:
   ```bash
   python run.py
   ```

## License

This project is licensed under the MIT License.
