import logging

class RequestLoggerMiddleware:
    def __init__(self, app):
        self.app = app
        self.logger = logging.getLogger("access")

    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD")
        path   = environ.get("PATH_INFO")
        self.logger.info(f"{method} {path}")
        return self.app(environ, start_response)
