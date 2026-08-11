import queue

from django.http import JsonResponse, StreamingHttpResponse
from django.views import View
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from .sse import subscribe, unsubscribe, format_sse, issue_ticket, consume_ticket
from .serializers import StreamTicketSerializer, SubmitResponseSerializer

HEARTBEAT_SECONDS = 15


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


def _event_stream(team_id):
    q = subscribe(team_id)
    try:
        yield ": connected\n\n"
        while True:
            try:
                event_type, data_json = q.get(timeout=HEARTBEAT_SECONDS)
                yield format_sse(event_type, data_json)
            except queue.Empty:
                yield ": heartbeat\n\n"
    finally:
        unsubscribe(team_id, q)


class TeamEventStreamView(View):
    """Server-Sent Events stream of the caller's team state.

    Pushes an event whenever the team is attacked (or attacks another team),
    so every connected client sees life/score/attack changes without
    polling. Authenticated via a single-use ticket from
    TeamStreamTicketView (see .sse.issue_ticket) rather than a bearer token
    in the query string. Single-process only, see users/sse.py.

    Plain Django View (not DRF's APIView) on purpose: APIView.initial()
    always runs content negotiation against Accept before the handler runs,
    which rejects EventSource's `Accept: text/event-stream` with a 406 even
    though this view returns a raw StreamingHttpResponse and never touches
    DRF's renderers.
    """

    def get(self, request):
        ticket = request.GET.get("ticket")
        team_id = consume_ticket(ticket) if ticket else None
        if team_id is None:
            return JsonResponse({"detail": "Invalid or expired ticket."}, status=401)

        response = StreamingHttpResponse(
            _event_stream(team_id), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
