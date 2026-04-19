"""ASGI config for portfolio_analyzer project."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portfolio_analyzer.settings")

application = get_asgi_application()
