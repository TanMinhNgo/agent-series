"""Compatibility facade for the FastAPI application.

The ASGI object and legacy direct imports remain available here while feature
controllers and routes are moved out of the entry point.
"""

import sys

from api import bootstrap as _application

sys.modules[__name__] = _application
