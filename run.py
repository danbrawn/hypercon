from app import create_app
from waitress import serve
import logging

# minimal logging
logging.basicConfig(level=logging.INFO)

app = create_app()

if __name__ == "__main__":
    serve(
      app,
      host="127.0.0.1",
      port=5000,
      expose_tracebacks=True,       # show error tracebacks in console
      channel_timeout=120
    )
