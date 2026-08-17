"""The team event stream, and the tickets that open it.

Unchanged in shape from the version this replaces: a normally-authenticated
POST mints a one-shot ticket, and the stream itself is opened with that ticket
in the query string so the long-lived JWT never lands in an access log.
"""
from django_bolt import Router, StreamingResponse
from django_bolt.auth import AllowAny
from django_bolt.exceptions import BadRequest, HTTPException

from config.concurrency import run_db
from config.security import DEFAULT_AUTH, DEFAULT_GUARDS

from .schemas import StreamTicketOut
from .sse import consume_ticket, format_sse, issue_ticket, subscribe

stream_router = Router(
    prefix="/api/teams", tags=["teams"],
    auth=DEFAULT_AUTH, guards=DEFAULT_GUARDS,
)


@stream_router.post("/stream-ticket/", summary="Issue an SSE stream ticket")
async def stream_ticket(request) -> StreamTicketOut:
    """Mint a short-lived, single-use ticket for opening the SSE stream.

    Authenticated normally, so the long-lived access token never has to travel
    in a URL — only this narrow, one-shot ticket does.
    """
    return await run_db(_issue_ticket, request)


def _issue_ticket(request):
    team = request.user.team
    if not team:
        raise BadRequest(detail="User is not part of any team.")
    return StreamTicketOut(ticket=issue_ticket(team.id))


async def _event_stream(team_id):
    async with subscribe(team_id) as events:
        # Subscribed before the client is told it is connected, so nothing
        # published after the browser's `onopen` can slip through the gap.
        yield ": connected\n\n"
        async for item in events:
            if item is None:
                # Also how a dropped connection gets noticed: writing this to
                # a closed socket is what ends an otherwise idle stream.
                yield ": heartbeat\n\n"
            else:
                event_type, data_json = item
                yield format_sse(event_type, data_json)


@stream_router.get(
    "/stream/",
    guards=[AllowAny()],
    summary="Team event stream",
    description=(
        "Server-Sent Events stream of the caller's team state. Pushes an event "
        "whenever the team is attacked (or attacks another team), so every "
        "connected client sees life/score/attack changes without polling."
    ),
)
async def team_event_stream(ticket: str | None = None):
    """Authenticated by the ticket alone, hence guards=[AllowAny()]: EventSource
    cannot set an Authorization header, so there is no bearer token to check.

    A raw StreamingResponse rather than Bolt's EventSourceResponse because this
    frames its own events — the `: connected` sentinel that closes the
    subscribe/announce race, and a heartbeat this code has to see in order to
    notice a dropped client.
    """
    # In-memory and lock-guarded, so it is safe to call straight from the
    # event loop — no database, nothing that can block.
    team_id = consume_ticket(ticket) if ticket else None
    if team_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired ticket.")

    return StreamingResponse(
        _event_stream(team_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Behind nginx the stream must not be response-buffered, or events
            # arrive in batches whenever the buffer happens to flush.
            "X-Accel-Buffering": "no",
        },
    )
