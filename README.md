# Onam Treasure Hunt

Django backend for the treasure hunt game. Teams answer their way around a
graph of nodes, attack each other, and watch their life/score/attack change
live over a Server-Sent Events stream.

The HTTP API is served by [django-bolt](https://github.com/dj-bolt/django-bolt),
which embeds a Rust/Actix server in the Django process. Django is still doing
all the Django things — models, migrations, admin, password hashing — but it no
longer sits in the request path for `/api/`. Anything Bolt does not route falls
through to Django's ASGI application, which is how `/admin/` still works.

## Running the server

**One process. Always.**

```sh
# production
python manage.py runbolt --host 0.0.0.0 --port 8000

# local development, with reload
python manage.py runbolt --dev
```

No gunicorn, no uvicorn, no worker class — `runbolt` *is* the server.

The single-process rule is the one thing not to get talked out of. Two pieces of
state live in plain process memory:

- **the team event pub/sub and its stream tickets** (`users/sse.py`), so the
  request that publishes an event has to share memory with the connection that
  receives it; and
- **the refresh-token revocation store** (`users/auth_api.py`), which is what
  stops a rotated-out refresh token from being replayed.

`runbolt --processes N` would give each process its own copy of both, silently
dropping cross-process events and letting a spent refresh token work again on a
different process. Running more than one process means putting a shared backend
(Redis, or similar) under `publish()`, the ticket store, and the revocation
store first.

One process is enough here: an idle SSE stream is a parked coroutine costing
nothing, request handling is genuinely concurrent, and the database is SQLite on
a single box, which serialises writes anyway.

Behind nginx, the stream endpoint needs response buffering off. The handler
already sends `X-Accel-Buffering: no` for this, so no nginx change should be
required.

### Static files

The admin's CSS is served by Bolt out of `STATIC_ROOT`, so deployments need

```sh
python manage.py collectstatic --no-input
```

before the admin will render with styling. Django's `runserver`-era behaviour of
finding admin static automatically no longer applies.

## Tests

```sh
python manage.py test
```

The suite drives the real Rust server through `django_bolt.testing.TestClient`.
Test cases that hit the database are `TransactionTestCase`, not `TestCase`:
handlers run their ORM work on a worker thread with its own connection, and
`TestCase`'s uncommitted wrapping transaction would lock SQLite against it.

## API

Unchanged from the DRF version it replaces — same paths, same request and
response bodies, same status codes — so no client needs touching. Tokens do not
survive the change, though: they are signed and structured differently, and
everyone logs in once more.

Interactive documentation is at `/api/docs/` (Swagger UI) and `/api/docs/redoc`,
with the raw OpenAPI document at `/api/schema/`.

Not carried over from djoser: the activation, password-reset and username-reset
endpoints. They all send mail, and no `EMAIL_BACKEND` was ever configured, so
they could not have worked.

## Layout

```
config/
  api.py           the single BoltAPI, assembled from each app's routers
  security.py      the default auth/guard posture every router applies
  concurrency.py   run_db(), which puts sync ORM work on a worker thread
  urls.py          only what Django itself still serves (the admin)
users/
  api.py           the game endpoints
  auth_api.py      registration, login, token refresh/verify, /users/me/
  sse_api.py       the team event stream and its tickets
  schemas.py       wire shapes, and the builders that fill them from models
  services.py      the game rules
  sse.py           in-process pub/sub and the ticket store
qr_generator/
  api.py           game-master exports (QR sheet PDF, node answer key CSV)
```

## Deploying

The GitHub Actions workflow runs `deploy-onam.sh` on the EC2 box, and that
script lives on the server rather than in this repository. It still starts the
old gunicorn command, so **it has to be updated to `manage.py runbolt`** before
this branch is deployed.
