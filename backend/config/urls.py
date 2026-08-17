"""
URL configuration for config project.

Only what Django itself still serves lives here. The JSON API moved to
django-bolt (users/api.py, qr_generator/api.py) and is routed in Rust before
Django is ever consulted; Bolt falls back to Django's ASGI application on a
route miss, which is what makes the admin below reachable. Bolt also reads
this urlconf to discover the admin prefix, so the admin path must stay here
even though nothing in Django dispatches it anymore.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
]

# Only mounted when SILK=1 (see settings). Like the admin, this is served by
# Django on Bolt's fallback path.
if settings.SILK_ENABLED:
    urlpatterns += [path('silk/', include('silk.urls', namespace='silk'))]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
