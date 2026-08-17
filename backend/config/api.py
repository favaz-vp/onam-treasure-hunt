"""The application's single BoltAPI, assembled from each app's routers.

Pointed at by ``settings.BOLT_API``, which is what ``manage.py runbolt`` loads.
One instance rather than one per app so the whole route table — and the OpenAPI
document generated from it — is defined in one place, and so tests can drive
the real thing with ``TestClient(api)``.

Anything not matched here falls through to Django's own ASGI application,
which is how /admin/ is still served.
"""
from django_bolt import (
    BoltAPI,
    OpenAPIConfig,
    RedocRenderPlugin,
    SwaggerRenderPlugin,
)
from django_bolt.auth import AllowAny

from qr_generator.api import qr_router
from users.api import node_router
from users.auth_api import auth_router
from users.sse_api import stream_router

# Swagger UI keeps drf-spectacular's /api/docs/, with ReDoc alongside it.
#
# `path` doubles as the prefix the schema generator skips when walking routes,
# so it cannot be "/api" — that would match every endpoint in the project and
# document none of them. "/api/docs" excludes only the documentation itself.
#
# Public, as drf-spectacular's SERVE_PERMISSIONS left them, which means opting
# out of the default IsAuthenticated guard.
openapi_config = OpenAPIConfig(
    title="Onam Treasure Hunt API",
    version="1.0.0",
    description=(
        "API documentation for Onam Treasure Hunt backend service featuring "
        "JWT authentication."
    ),
    path="/api/docs",
    render_plugins=[
        SwaggerRenderPlugin(path="/"),
        RedocRenderPlugin(path="/redoc"),
    ],
    guards=[AllowAny()],
)

# trailing_slash="append" keeps the URLs DRF's DefaultRouter produced, so
# clients pointed at e.g. /api/nodes/3/submit/ do not have to change.
api = BoltAPI(trailing_slash="append", openapi_config=openapi_config)

api.include_router(auth_router)
api.include_router(node_router)
api.include_router(stream_router)
api.include_router(qr_router)


@api.get("/api/schema/", guards=[AllowAny()], include_in_schema=False)
async def schema():
    """The raw OpenAPI document, on the URL drf-spectacular published it at.

    Bolt serves its own copy under the docs prefix, but code generators and CI
    checks in this project point at /api/schema/, so it keeps answering there.
    """
    from django_bolt.openapi.schema_generator import SchemaGenerator

    if api._openapi_schema is None:
        api._openapi_schema = SchemaGenerator(api, openapi_config).generate().to_schema()
    return api._openapi_schema
