"""The authentication endpoints.

These assert the wire contract djoser + SimpleJWT used to provide, because
clients were written against it and the reimplementation is only worth
anything if it is indistinguishable from the outside.
"""
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from config.api import api
from django_bolt.testing import TestClient

User = get_user_model()


# TransactionTestCase, not TestCase: the handlers run their ORM work on a
# worker thread, which uses its own database connection. TestCase wraps each
# test in an uncommitted transaction on the main thread's connection, and
# SQLite then locks the worker out ("database table is locked"). This is the
# same reason Django's own LiveServerTestCase is a TransactionTestCase.
class AuthEndpointTests(TransactionTestCase):
    register_url = '/api/auth/users/'
    jwt_create_url = '/api/auth/jwt/create/'
    jwt_refresh_url = '/api/auth/jwt/refresh/'
    jwt_verify_url = '/api/auth/jwt/verify/'
    user_me_url = '/api/auth/users/me/'

    user_email = 'testuser@example.com'
    user_password = 'Password123!'

    def setUp(self):
        self.client = self.enterContext(TestClient(api))

    def _login(self, **overrides):
        payload = {'email': self.user_email, 'password': self.user_password}
        payload.update(overrides)
        return self.client.post(self.jwt_create_url, json=payload)

    def _auth_header(self, access):
        return {'Authorization': f'Bearer {access}'}

    def test_user_registration(self):
        response = self.client.post(self.register_url, json={
            'email': self.user_email,
            'password': self.user_password,
            're_password': self.user_password,
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(),
            {'email': self.user_email, 'id': User.objects.get().id},
        )
        self.assertTrue(User.objects.filter(email=self.user_email).exists())

    def test_registration_assigns_a_team(self):
        self.client.post(self.register_url, json={
            'email': self.user_email,
            'password': self.user_password,
            're_password': self.user_password,
        })

        self.assertIsNotNone(User.objects.get().team)

    def test_registration_rejects_mismatched_passwords(self):
        response = self.client.post(self.register_url, json={
            'email': self.user_email,
            'password': self.user_password,
            're_password': 'SomethingElse123!',
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {'non_field_errors': ["The two password fields didn't match."]},
        )
        self.assertFalse(User.objects.exists())

    def test_registration_rejects_a_duplicate_email(self):
        User.objects.create_user(email=self.user_email, password=self.user_password)

        response = self.client.post(self.register_url, json={
            'email': self.user_email,
            'password': self.user_password,
            're_password': self.user_password,
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {'email': ['user with this email address already exists.']},
        )

    def test_registration_enforces_the_password_validators(self):
        response = self.client.post(self.register_url, json={
            'email': self.user_email,
            'password': '123',
            're_password': '123',
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.json())
        self.assertFalse(User.objects.exists())

    def test_jwt_create_returns_a_token_pair(self):
        User.objects.create_user(email=self.user_email, password=self.user_password)

        response = self._login()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {'access', 'refresh'})

    def test_jwt_create_rejects_a_bad_password(self):
        User.objects.create_user(email=self.user_email, password=self.user_password)

        response = self._login(password='wrong-password')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {'detail': 'No active account found with the given credentials'},
        )

    def test_jwt_create_rejects_an_inactive_user(self):
        user = User.objects.create_user(email=self.user_email, password=self.user_password)
        user.is_active = False
        user.save(update_fields=['is_active'])

        self.assertEqual(self._login().status_code, 401)

    def test_me_returns_the_caller_with_their_team(self):
        user = User.objects.create_user(email=self.user_email, password=self.user_password)
        access = self._login().json()['access']

        response = self.client.get(self.user_me_url, headers=self._auth_header(access))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['email'], self.user_email)
        self.assertEqual(body['id'], user.id)
        self.assertEqual(body['team']['id'], user.team_id)
        self.assertEqual(body['team']['members'], [{'id': user.id, 'email': user.email}])

    def test_me_requires_a_token(self):
        response = self.client.get(self.user_me_url)

        self.assertEqual(response.status_code, 401)

    def test_me_rejects_a_garbage_token(self):
        response = self.client.get(
            self.user_me_url, headers=self._auth_header('not-a-jwt')
        )

        self.assertEqual(response.status_code, 401)

    def test_refresh_returns_a_new_pair(self):
        User.objects.create_user(email=self.user_email, password=self.user_password)
        refresh = self._login().json()['refresh']

        response = self.client.post(self.jwt_refresh_url, json={'refresh': refresh})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {'access', 'refresh'})

    def test_the_new_access_token_works(self):
        User.objects.create_user(email=self.user_email, password=self.user_password)
        refresh = self._login().json()['refresh']

        access = self.client.post(
            self.jwt_refresh_url, json={'refresh': refresh}
        ).json()['access']
        response = self.client.get(self.user_me_url, headers=self._auth_header(access))

        self.assertEqual(response.status_code, 200)

    def test_a_spent_refresh_token_is_rejected(self):
        # Rotation is on, so exchanging a refresh token retires it — this is
        # what ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION used to do.
        User.objects.create_user(email=self.user_email, password=self.user_password)
        refresh = self._login().json()['refresh']
        self.client.post(self.jwt_refresh_url, json={'refresh': refresh})

        response = self.client.post(self.jwt_refresh_url, json={'refresh': refresh})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'token_not_valid')

    def test_refresh_rejects_an_access_token(self):
        User.objects.create_user(email=self.user_email, password=self.user_password)
        access = self._login().json()['access']

        response = self.client.post(self.jwt_refresh_url, json={'refresh': access})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'token_not_valid')

    def test_verify_accepts_a_live_token_and_rejects_a_bogus_one(self):
        User.objects.create_user(email=self.user_email, password=self.user_password)
        access = self._login().json()['access']

        self.assertEqual(
            self.client.post(self.jwt_verify_url, json={'token': access}).status_code,
            200,
        )

        response = self.client.post(self.jwt_verify_url, json={'token': 'nonsense'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'token_not_valid')
