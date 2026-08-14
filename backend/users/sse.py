"""In-process pub/sub for pushing team state updates to connected SSE
clients, plus a matching store for the short-lived stream tickets.

Both live in plain process memory, which is only correct because the whole
app is served by a *single* ASGI process (see README.md): the request that
publishes an event always shares memory with the connection that has to
receive it.

This used to be backed by Redis. That was needed only because sync gunicorn
workers pin an entire worker process per open stream, so the app had to run
several workers just to stay reachable — and then the worker issuing a
ticket or publishing an event was rarely the one holding the browser's
stream. Under ASGI an idle stream costs one parked coroutine instead of a
worker, one process is enough, and the broker became dead weight.

If this ever has to span multiple processes again, publish() and the ticket
store are the two things that need a shared backend put back underneath.
"""
import asyncio
import json
import secrets
import threading
import time
from contextlib import asynccontextmanager

TICKET_TTL_SECONDS = 30
HEARTBEAT_SECONDS = 15

# Per-connection backlog. Every event carries the team's full stats, so a
# client slow enough to overflow this loses nothing that the events queued
# behind it don't already say.
MAX_QUEUED_EVENTS = 64

# ticket -> (team_id, expires_at). Locked because tickets are issued from a
# sync view (a thread) and redeemed from the event loop.
_tickets = {}
_tickets_lock = threading.Lock()

# team_id -> set of _Subscriber. Locked for the same reason: publish() is
# called from sync code running in Django's thread executor, while
# subscribe() runs on the event loop.
_subscribers = {}
_subscribers_lock = threading.Lock()


def _purge_expired_tickets(now):
    """Drop timed-out tickets. Caller must hold _tickets_lock."""
    for ticket in [t for t, (_, expires_at) in _tickets.items() if expires_at <= now]:
        del _tickets[ticket]


def issue_ticket(team_id):
    """Mint a short-lived, single-use ticket for opening the SSE stream.

    Keeps the long-lived JWT out of the stream URL (and therefore out of
    server access logs, browser history, and Referer headers).
    """
    ticket = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _tickets_lock:
        # Nothing else sweeps this dict, so unredeemed tickets are collected
        # here, on the next mint.
        _purge_expired_tickets(now)
        _tickets[ticket] = (team_id, now + TICKET_TTL_SECONDS)
    return ticket


def consume_ticket(ticket):
    """Redeem a ticket for its team_id. Each ticket works exactly once.

    The pop under the lock is what makes it single-use: two requests racing
    to redeem the same ticket, only one gets the team_id.
    """
    with _tickets_lock:
        entry = _tickets.pop(ticket, None)
    if entry is None:
        return None
    team_id, expires_at = entry
    return team_id if expires_at > time.monotonic() else None


class _Subscriber:
    """One connected client: a queue, plus the loop allowed to touch it.

    publish() runs on whichever thread served the write that triggered it —
    the DRF views and the admin are sync, so under ASGI that's a thread from
    Django's executor, never the event loop. Every queue mutation therefore
    has to be handed back to the owning loop.
    """

    def __init__(self):
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue(maxsize=MAX_QUEUED_EVENTS)

    def deliver(self, message):
        try:
            self.loop.call_soon_threadsafe(self._enqueue, message)
        except RuntimeError:
            # Loop already closed: the client is gone and its unsubscribe
            # simply hasn't run yet. Nothing to deliver to.
            pass

    def _enqueue(self, message):
        # Runs on the event loop.
        if self.queue.full():
            self.queue.get_nowait()  # drop the oldest, keep the freshest state
        self.queue.put_nowait(message)


async def _events(queue):
    """Yield (event_type, data_json) as they arrive, parking in between, and
    yield None roughly every HEARTBEAT_SECONDS of silence so the caller can
    send a keep-alive.
    """
    while True:
        try:
            yield await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
        except TimeoutError:
            yield None


@asynccontextmanager
async def subscribe(team_id):
    """Register as a listener for a team and hand back its event stream.

    A context manager rather than a plain generator so the caller can be
    sure it is subscribed *before* it announces the connection: a generator
    only registers once something pulls its first value, which would leave a
    window where events published to an already-open stream are dropped.
    """
    subscriber = _Subscriber()
    with _subscribers_lock:
        _subscribers.setdefault(team_id, set()).add(subscriber)
    try:
        yield _events(subscriber.queue)
    finally:
        # Deliberately sync-only: this also runs on GeneratorExit when the
        # client disconnects, where awaiting is not allowed.
        with _subscribers_lock:
            team_subscribers = _subscribers.get(team_id)
            if team_subscribers is not None:
                team_subscribers.discard(subscriber)
                if not team_subscribers:
                    del _subscribers[team_id]


def publish(team_id, event_type, data):
    """Push an event to every listener currently subscribed to a team.

    Safe to call from sync code on any thread.
    """
    message = (event_type, json.dumps(data))
    with _subscribers_lock:
        subscribers = list(_subscribers.get(team_id, ()))
    for subscriber in subscribers:
        subscriber.deliver(message)


def format_sse(event_type, data_json):
    return f"event: {event_type}\ndata: {data_json}\n\n"
