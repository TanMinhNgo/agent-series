"""Stable ASGI entry point.

Deployment commands intentionally keep using ``api.main:app``.  The application
composition and HTTP handlers live in :mod:`api.app` so this module remains a
small compatibility boundary rather than another place for route logic.
"""

import sys

from . import app as _application

# Make ``import api.main`` expose the same module object as ``api.app``.  This
# preserves existing tests and integrations that monkeypatch module helpers.
sys.modules[__name__] = _application
