from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

User = get_user_model()


class DjoserJWTAuthTestCase(APITestCase):
    def setUp(self):
        self.register_url = '/api/auth/users/'
        self.jwt_create_url = '/api/auth/jwt/create/'
        self.jwt_refresh_url = '/api/auth/jwt/refresh/'
        self.user_me_url = '/api/auth/users/me/'

        self.user_email = 'testuser@example.com'
        self.user_password = 'Password123!'

    def test_user_registration(self):
        data = {
            'email': self.user_email,
            'password': self.user_password,
            're_password': self.user_password,
        }
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email=self.user_email).exists())

    def test_jwt_create_refresh_and_authenticated_request(self):
        # 1. Create User
        user = User.objects.create_user(email=self.user_email, password=self.user_password)

        # 2. Get JWT Tokens
        login_data = {
            'email': self.user_email,
            'password': self.user_password,
        }
        response = self.client.post(self.jwt_create_url, login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

        access_token = response.data['access']
        refresh_token = response.data['refresh']

        # 3. Access Protected Endpoint (/api/auth/users/me/)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        me_response = self.client.get(self.user_me_url)
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data['email'], self.user_email)

        # 4. Refresh Token
        refresh_data = {'refresh': refresh_token}
        self.client.credentials()  # Reset auth header
        refresh_response = self.client.post(self.jwt_refresh_url, refresh_data, format='json')
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        self.assertIn('access', refresh_response.data)
