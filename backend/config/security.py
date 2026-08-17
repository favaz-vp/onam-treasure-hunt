"""The default authentication posture for every router in the project.

Deliberately not ``BOLT_AUTHENTICATION_CLASSES`` / ``BOLT_DEFAULT_PERMISSION_CLASSES``
in settings.py: Bolt wants instances rather than import paths there, and
constructing a JWTAuthentication reads SECRET_KEY — so a settings module that
built one would be reading settings while settings were still being defined.
That works by accident for config.settings itself and breaks for anything that
layers on top of it (``from config.settings import *``).

Here the import happens well after django.setup(), and every router names its
posture explicitly. Individual routes opt out with guards=[AllowAny()]:
registration, login, token refresh/verify, the ticketed SSE stream, and the
API documentation.
"""
from django_bolt.auth import IsAuthenticated, JWTAuthentication

# Attempted on every request; guards are what actually reject.
DEFAULT_AUTH = [JWTAuthentication()]

# Default-deny, matching DRF's DEFAULT_PERMISSION_CLASSES before the port.
DEFAULT_GUARDS = [IsAuthenticated()]
