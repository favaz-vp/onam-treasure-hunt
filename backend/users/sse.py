"""Redis-backed pub/sub for pushing team state updates to connected SSE
clients, plus a matching Redis-backed store for the short-lived stream
tickets.

Both used to be plain in-process dicts. That only works under a single
process: gunicorn with more than one worker (or multiple replicas) means
the process that issues a ticket or calls publish() is not necessarily the
process holding a given browser's SSE connection, so an in-memory store
silently misses cross-process traffic — tickets "expire" immediately and
published events never reach the listener. Redis gives every worker a
shared store instead, so tickets and events work regardless of which
process handles which request.
"""
import json
import secrets

from django.conf import settings
from redis import Redis

TICKET_TTL_SECONDS = 30
HEARTBEAT_SECONDS = 15

_redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)

# GET+DEL as one atomic step, so a ticket can only ever be consumed once
# even if two requests race to redeem it at the same instant.
_consume_ticket_script = _redis.register_script(
    """
    local value = redis.call('GET', KEYS[1])
    if value then
        redis.call('DEL', KEYS[1])
    end
    return value
    """
)


def _ticket_key(ticket):
    return f"sse:ticket:{ticket}"


def _team_channel(team_id):
    return f"sse:team:{team_id}"


def issue_ticket(team_id):
    """Mint a short-lived, single-use ticket for opening the SSE stream.

    Keeps the long-lived JWT out of the stream URL (and therefore out of
    server access logs, browser history, and Referer headers).
    """
    ticket = secrets.token_urlsafe(32)
    _redis.setex(_ticket_key(ticket), TICKET_TTL_SECONDS, team_id)
    return ticket


def consume_ticket(ticket):
    """Redeem a ticket for its team_id. Each ticket works exactly once."""
    team_id = _consume_ticket_script(keys=[_ticket_key(ticket)])
    return int(team_id) if team_id is not None else None


def publish(team_id, event_type, data):
    """Push an event to every listener currently subscribed to a team."""
    _redis.publish(_team_channel(team_id), json.dumps({"event": event_type, "data": data}))


def format_sse(event_type, data_json):
    return f"event: {event_type}\ndata: {data_json}\n\n"


def listen(team_id):
    """Yield (event_type, data_json) for every event published to a team,
    blocking between messages. Yields None roughly every
    HEARTBEAT_SECONDS with no message, so the caller can send a keep-alive.
    """
    pubsub = _redis.pubsub()
    pubsub.subscribe(_team_channel(team_id))
    try:
        while True:
            message = pubsub.get_message(
                timeout=HEARTBEAT_SECONDS, ignore_subscribe_messages=True
            )
            if message is None:
                yield None
                continue
            payload = json.loads(message["data"])
            yield payload["event"], json.dumps(payload["data"])
    finally:
        pubsub.unsubscribe(_team_channel(team_id))
        pubsub.close()
