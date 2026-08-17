"""The game-master exports.

Worth covering mostly for their edges: both endpoints are superuser-only, and
the PDF one takes a multipart upload, which is the part of the request binding
most easily got wrong.
"""
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from config.api import api
from django_bolt.testing import TestClient
from users.models import Node

User = get_user_model()

VALID_CSV = b"id,caption\n1,First clue\n2,Second clue\n"


class ExportTestCase(TransactionTestCase):
    def setUp(self):
        self.client = self.enterContext(TestClient(api))
        User.objects.create_superuser(email="gm@example.com", password="Password123!")
        User.objects.create_user(email="player@example.com", password="Password123!")

    def token(self, email):
        response = self.client.post(
            "/api/auth/jwt/create/",
            json={"email": email, "password": "Password123!"},
        )
        return {"Authorization": f"Bearer {response.json()['access']}"}

    @property
    def gm(self):
        return self.token("gm@example.com")

    @property
    def player(self):
        return self.token("player@example.com")


class GenerateQRPDFTests(ExportTestCase):
    url = "/api/generate/pdf/"

    def post_csv(self, headers, content=VALID_CSV, filename="nodes.csv"):
        return self.client.post(
            self.url, headers=headers, files={"file": (filename, content, "text/csv")}
        )

    def test_a_superuser_gets_a_pdf(self):
        response = self.post_csv(self.gm)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertEqual(
            response.headers["content-disposition"],
            'attachment; filename="qr_codes.pdf"',
        )
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_an_ordinary_player_is_refused(self):
        response = self.post_csv(self.player)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {"detail": "You do not have permission to access this resource."},
        )

    def test_anonymous_is_refused(self):
        self.assertEqual(self.post_csv({}).status_code, 401)

    def test_only_csv_uploads_are_accepted(self):
        response = self.post_csv(self.gm, filename="nodes.txt")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"file": ["Only CSV files are allowed."]})

    def test_a_csv_missing_its_columns_is_reported(self):
        response = self.post_csv(self.gm, content=b"nope\n1\n")

        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())


class GenerateNodeCSVTests(ExportTestCase):
    url = "/api/generate/csv/"

    def test_a_superuser_gets_the_answer_key(self):
        first = Node.objects.create(data="first", answer="alpha")
        second = Node.objects.create(data="second", answer="beta")
        first.next_node = second
        first.save()

        response = self.client.get(self.url, headers=self.gm)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/csv")
        rows = response.content.decode().splitlines()
        self.assertEqual(rows[0], "id,caption")
        # Each row pairs a node's answer with the node it unlocks.
        self.assertIn(f"{second.id},alpha", rows)

    def test_an_ordinary_player_is_refused(self):
        response = self.client.get(self.url, headers=self.player)

        self.assertEqual(response.status_code, 403)

    def test_anonymous_is_refused(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
