from app import create_app
from waitress import serve
import logging
"""

# минимум логинг
logging.basicConfig(level=logging.INFO)

app = create_app()

if __name__ == "__main__":
    serve(
      app,
      host="127.0.0.1",
      port=5000,
      expose_tracebacks=True,       # показва traceback на грешки в конзолата
      channel_timeout=120
    )

"""

import sys, os, scipy
print("PYTHON", sys.executable)
print("VENV", os.environ.get("VIRTUAL_ENV"))
print("SCIPY", scipy.__file__)
