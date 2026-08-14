from django.http import JsonResponse, StreamingHttpResponse
from django.views import View
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from .sse import subscribe, format_sse, issue_ticket, consume_ticket
from .serializers import StreamTicketSerializer, SubmitResponseSerializer


class TeamStreamTicketView(APIView):
    """Issue a short-lived, single-use ticket for opening the SSE stream.

    Authenticated normally (JWT via Authorization header), so the long-lived
    access token never has to travel in a URL — only this narrow, one-shot
    ticket does.
    """

    @extend_schema(
        request=None,
        responses={200: StreamTicketSerializer, 400: SubmitResponseSerializer},
    )
    def post(self, request):
        team = request.user.team
        if not team:
            return Response({"detail": "User is not part of any team."}, status=400)
        return Response({"ticket": issue_ticket(team.id)})


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


class TeamEventStreamView(View):
    """Server-Sent Events stream of the caller's team state.

    Pushes an event whenever the team is attacked (or attacks another team),
    so every connected client sees life/score/attack changes without
    polling. Authenticated via a single-use ticket from
    TeamStreamTicketView (see .sse.issue_ticket) rather than a bearer token
    in the query string.

    Async, and only correct on an ASGI server: an open stream then costs a
    parked coroutine instead of a whole worker process, which is what let
    the Redis broker go away (see users/sse.py). Under WSGI Django has to
    drain an async iterator before it can respond, so this endpoint would
    hang forever — `manage.py runserver` included. Run uvicorn locally.

    Plain Django View (not DRF's APIView) on purpose: APIView.initial()
    always runs content negotiation against Accept before the handler runs,
    which rejects EventSource's `Accept: text/event-stream` with a 406 even
    though this view returns a raw StreamingHttpResponse and never touches
    DRF's renderers.
    """

    async def get(self, request):
        ticket = request.GET.get("ticket")
        # In-memory and lock-guarded, so it is safe to call straight from the
        # event loop — no database, nothing that can block.
        team_id = consume_ticket(ticket) if ticket else None
        if team_id is None:
            return JsonResponse({"detail": "Invalid or expired ticket."}, status=401)

        response = StreamingHttpResponse(
            _event_stream(team_id), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
