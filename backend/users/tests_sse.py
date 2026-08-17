import asyncio
import time

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TransactionTestCase

from config.api import api
from django_bolt.testing import TestClient

from . import sse
from .sse import consume_ticket, issue_ticket, publish, subscribe
from .sse_api import _event_stream, team_event_stream

User = get_user_model()

TEAM_ID = 1

# Long enough that a hung stream fails the test instead of hanging the run,
# short enough that a real failure is reported quickly.
READ_TIMEOUT = 5


def _reset_sse_state():
    sse._tickets.clear()
    sse._subscribers.clear()


async def _read(stream):
    """Pull one item, refusing to wait forever for it."""
    return await asyncio.wait_for(anext(stream), timeout=READ_TIMEOUT)


class TicketStoreTests(SimpleTestCase):
    def tearDown(self):
        _reset_sse_state()

    def test_ticket_redeems_for_its_team(self):
        ticket = issue_ticket(TEAM_ID)
        self.assertEqual(consume_ticket(ticket), TEAM_ID)

    def test_ticket_works_only_once(self):
        ticket = issue_ticket(TEAM_ID)
        consume_ticket(ticket)
        self.assertIsNone(consume_ticket(ticket))

    def test_unknown_ticket_is_rejected(self):
        self.assertIsNone(consume_ticket("never-issued"))

    def test_expired_ticket_is_rejected(self):
        ticket = issue_ticket(TEAM_ID)
        # Backdate it rather than sleep out the real 30s TTL.
        sse._tickets[ticket] = (TEAM_ID, time.monotonic() - 1)
        self.assertIsNone(consume_ticket(ticket))

    def test_issuing_collects_expired_tickets(self):
        stale = issue_ticket(TEAM_ID)
        sse._tickets[stale] = (TEAM_ID, time.monotonic() - 1)

        issue_ticket(TEAM_ID)

        self.assertNotIn(stale, sse._tickets)


class PubSubTests(SimpleTestCase):
    def tearDown(self):
        _reset_sse_state()

    def test_publish_without_listeners_is_a_no_op(self):
        publish(TEAM_ID, "team_update", {"life": 3})

    async def test_subscriber_receives_published_event(self):
        async with subscribe(TEAM_ID) as events:
            publish(TEAM_ID, "team_attacked", {"life": 2})

            self.assertEqual(
                await _read(events), ("team_attacked", '{"life": 2}')
            )

    async def test_events_reach_every_subscriber_of_that_team(self):
        async with subscribe(TEAM_ID) as first, subscribe(TEAM_ID) as second:
            publish(TEAM_ID, "team_update", {"life": 4})

            self.assertEqual(await _read(first), ("team_update", '{"life": 4}'))
            self.assertEqual(await _read(second), ("team_update", '{"life": 4}'))

    async def test_events_do_not_leak_to_other_teams(self):
        async with subscribe(TEAM_ID) as events:
            publish(TEAM_ID + 1, "team_update", {"life": 4})
            publish(TEAM_ID, "team_update", {"life": 1})

            # The other team's event never enters this queue, so this is the
            # first thing read rather than the second.
            self.assertEqual(await _read(events), ("team_update", '{"life": 1}'))

    async def test_publish_from_a_worker_thread_reaches_the_loop(self):
        # The real callers all run their ORM work on a worker thread (see
        # config/concurrency.py), so they publish from off the event loop.
        async with subscribe(TEAM_ID) as events:
            await asyncio.to_thread(publish, TEAM_ID, "team_update", {"life": 5})

            self.assertEqual(await _read(events), ("team_update", '{"life": 5}'))

    async def test_backlog_overflow_drops_oldest_and_keeps_newest(self):
        async with subscribe(TEAM_ID) as events:
            overflow = sse.MAX_QUEUED_EVENTS + 1
            for life in range(overflow):
                publish(TEAM_ID, "team_update", {"life": life})
            # publish() hands work to the loop via call_soon_threadsafe; give
            # those callbacks a chance to run before reading.
            await asyncio.sleep(0)

            received = [
                await _read(events) for _ in range(sse.MAX_QUEUED_EVENTS)
            ]

        lives = [data for _, data in received]
        self.assertEqual(lives[0], '{"life": 1}')  # the oldest was dropped
        self.assertEqual(lives[-1], f'{{"life": {overflow - 1}}}')

    async def test_unsubscribes_when_the_stream_closes(self):
        async with subscribe(TEAM_ID):
            self.assertEqual(len(sse._subscribers[TEAM_ID]), 1)

        self.assertNotIn(TEAM_ID, sse._subscribers)


class EventStreamTests(SimpleTestCase):
    """The stream endpoint. Driven directly rather than over HTTP: the stream
    never ends, and the test client buffers a response to completion before
    handing it back, so an HTTP-level read of it would simply hang.

    No database either — the handler authenticates from the in-memory ticket
    store and never queries.
    """

    def tearDown(self):
        _reset_sse_state()

    async def test_stream_delivers_events_for_the_ticketed_team(self):
        response = await team_event_stream(ticket=issue_ticket(TEAM_ID))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-cache")
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")

        body = aiter(response.content)
        # Reading this back means the subscription is live, so the publish
        # below cannot race it.
        self.assertEqual(await _read(body), ": connected\n\n")

        publish(TEAM_ID, "team_attacked", {"life": 2, "damage": 1})

        self.assertEqual(
            await _read(body),
            'event: team_attacked\ndata: {"life": 2, "damage": 1}\n\n',
        )

        await body.aclose()

    async def test_stream_is_an_event_stream(self):
        response = await team_event_stream(ticket=issue_ticket(TEAM_ID))

        self.assertEqual(response.media_type, "text/event-stream")

    async def test_client_disconnect_unsubscribes(self):
        # Closing the response generator is what the server does when the
        # browser goes away.
        stream = _event_stream(TEAM_ID)
        await _read(stream)  # ": connected", i.e. subscribed

        self.assertEqual(len(sse._subscribers[TEAM_ID]), 1)

        await stream.aclose()

        self.assertNotIn(TEAM_ID, sse._subscribers)


class StreamEndpointAuthTests(SimpleTestCase):
    """The one part of the stream endpoint that answers with a finite response,
    so it can be exercised over real HTTP."""

    def setUp(self):
        self.client = self.enterContext(TestClient(api))

    def tearDown(self):
        _reset_sse_state()

    def test_rejects_a_missing_or_spent_ticket(self):
        ticket = issue_ticket(TEAM_ID)
        consume_ticket(ticket)

        for query in ("", f"?ticket={ticket}", "?ticket=bogus"):
            with self.subTest(query=query):
                response = self.client.get(f"/api/teams/stream/{query}")

                self.assertEqual(response.status_code, 401)
                self.assertEqual(
                    response.json(), {"detail": "Invalid or expired ticket."}
                )


class StreamTicketEndpointTests(TransactionTestCase):
    def setUp(self):
        self.client = self.enterContext(TestClient(api))
        self.user = User.objects.create_user(
            email="captain@example.com", password="Password123!"
        )

    def tearDown(self):
        _reset_sse_state()

    def _auth(self):
        response = self.client.post(
            "/api/auth/jwt/create/",
            json={"email": "captain@example.com", "password": "Password123!"},
        )
        return {"Authorization": f"Bearer {response.json()['access']}"}

    def test_issues_a_ticket_for_the_callers_team(self):
        response = self.client.post(
            "/api/teams/stream-ticket/", headers=self._auth()
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            consume_ticket(response.json()["ticket"]), self.user.team_id
        )

    def test_rejects_a_user_without_a_team(self):
        headers = self._auth()
        self.user.team = None
        self.user.save(update_fields=["team"])

        response = self.client.post("/api/teams/stream-ticket/", headers=headers)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"detail": "User is not part of any team."}
        )

    def test_requires_authentication(self):
        response = self.client.post("/api/teams/stream-ticket/")

        self.assertEqual(response.status_code, 401)
