"""In-process pub/sub for pushing team state updates to connected SSE clients.

Assumes a single-process deployment (or per-team affinity). If the app ever
runs behind multiple gunicorn/uvicorn workers or replicas, this in-memory
registry only reaches listeners connected to the same process — swap for a
shared broker (e.g. Redis pub/sub) at that point.
"""
import json
import queue
import secrets
import threading
import time

_lock = threading.Lock()
_listeners = {}  # team_id -> set[queue.Queue]

_tickets_lock = threading.Lock()
_tickets = {}  # ticket -> (team_id, expires_at)
TICKET_TTL_SECONDS = 30


def subscribe(team_id):
    """Register a new listener queue for a team and return it."""
    q = queue.Queue(maxsize=100)
    with _lock:
        _listeners.setdefault(team_id, set()).add(q)
    return q


def unsubscribe(team_id, q):
    with _lock:
        listeners = _listeners.get(team_id)
        if listeners is not None:
            listeners.discard(q)
            if not listeners:
                _listeners.pop(team_id, None)


def publish(team_id, event_type, data):
    """Push an event to every listener currently subscribed to a team."""
    with _lock:
        listeners = list(_listeners.get(team_id, ()))
    payload = json.dumps(data)
    for q in listeners:
        try:
            q.put_nowait((event_type, payload))
        except queue.Full:
            # Slow consumer; drop the event rather than block the publisher.
            pass


def format_sse(event_type, data_json):
    return f"event: {event_type}\ndata: {data_json}\n\n"


def issue_ticket(team_id):
    """Mint a short-lived, single-use ticket for opening the SSE stream.

    Keeps the long-lived JWT out of the stream URL (and therefore out of
    server access logs, browser history, and Referer headers).
    """
    ticket = secrets.token_urlsafe(32)
    with _tickets_lock:
        _tickets[ticket] = (team_id, time.time() + TICKET_TTL_SECONDS)
    return ticket


def consume_ticket(ticket):
    """Redeem a ticket for its team_id. Each ticket works exactly once."""
    with _tickets_lock:
        entry = _tickets.pop(ticket, None)
    if entry is None:
        return None
    team_id, expires_at = entry
    if time.time() > expires_at:
        return None
    return team_id
