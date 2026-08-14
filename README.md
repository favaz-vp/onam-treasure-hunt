# Onam Treasure Hunt

Django backend for the treasure hunt game. Teams answer their way around a
graph of nodes, attack each other, and watch their life/score/attack change
live over a Server-Sent Events stream.

## Running the server

**The app must be served over ASGI, as a single process.**

```sh
# production
gunicorn config.asgi:application \
    -k uvicorn_worker.UvicornWorker \
    -w 1 \
    --graceful-timeout 5 \
    -b 0.0.0.0:8000

# local development
uvicorn config.asgi:application --reload
```

Both halves of that matter:

- **ASGI, not WSGI.** `/api/teams/stream/` holds a connection open for as long
  as a player has the game open. A sync WSGI worker can only serve one request
  at a time, so every open stream permanently consumed a whole worker and the
  API stopped answering once players outnumbered workers. Under ASGI an idle
  stream is a parked coroutine costing nothing. `manage.py runserver` is WSGI
  and will hang on the stream endpoint — use uvicorn locally.

- **One worker.** Stream tickets and the team event pub/sub live in process
  memory (`users/sse.py`), so the request that publishes an event has to share
  memory with the connection that receives it. A second worker would silently
  drop cross-process events. Running multiple processes again means putting a
  shared broker (Redis, or similar) back under `publish()` and the ticket store.

  One process is enough here: streams are effectively free, and the database is
  SQLite on a single box, which serialises writes anyway.

`--graceful-timeout 5` is worth setting because open streams never finish on
their own — at gunicorn's default of 30s, every deploy stalls for the full
half minute before the new code comes up.

Behind nginx, the stream endpoint needs response buffering off. The view already
sends `X-Accel-Buffering: no` for this, so no nginx change should be required.

## Tests

```sh
python manage.py test
```
