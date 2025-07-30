# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""Command-line helper to run the DB-based optimization."""

from pprint import pprint

from app import create_app
from app.optimize import run_full_optimization


def main():
    app = create_app()
    with app.app_context():
        result = run_full_optimization()
    if result is None:
        print("Optimization failed")
    else:
        pprint(result)


if __name__ == "__main__":
    main()
