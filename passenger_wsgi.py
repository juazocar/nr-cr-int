"""
Entrada para cPanel / LiteSpeed Passenger.

FastAPI es ASGI y Passenger normalmente espera WSGI. Este adaptador utiliza
a2wsgi para presentar la aplicación FastAPI como una aplicación WSGI.
"""
from a2wsgi import ASGIMiddleware
from app.main import app as asgi_app

application = ASGIMiddleware(asgi_app)
