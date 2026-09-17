"""Stable ASGI entry point.

Deployment commands intentionally keep using ``api.main:app``. Application
composition is loaded through :mod:`api.app`; this module remains a stable
compatibility boundary for tests and integrations.
"""

import sys

from . import app as _application

# Make ``import api.main`` expose the same module object as ``api.app``.  This
# preserves existing tests and integrations that monkeypatch module helpers.
sys.modules[__name__] = _application
