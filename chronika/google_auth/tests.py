from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache, caches
from django.http import HttpResponse
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from google_auth.models import GoogleRefreshToken
from google_auth.services import (
    get_user_credentials,
    get_user_token,
    save_google_refresh_token,
    set_refresh_cookie,
    store_user_token,
)
from users.models import CustomUser


class GoogleAuthApiTests(APITestCase):
    @patch("google_auth.apis.GoogleRawLoginFlowService")
    def test_google_redirect_returns_auth_url(self, mocked_flow_class):
        mocked_flow = mocked_flow_class.return_value
        mocked_flow.get_authorization_url.return_value = (
            "https://accounts.google.com/mock-auth",
            "state-123",
        )

        url = reverse("google_auth:google_auth_redirect")
        response = self.client.get(f"{url}?consent=true")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["auth_url"], "https://accounts.google.com/mock-auth")
        mocked_flow.get_authorization_url.assert_called_once_with(consent=True)

    def test_google_callback_requires_code_and_state(self):
        url = reverse("google_auth:google_callback")
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("google_auth.apis.set_refresh_cookie")
    @patch("google_auth.apis.AuthService")
    @patch("google_auth.apis.GoogleRawLoginFlowService")
    def test_google_callback_returns_access_token_for_existing_user(
        self,
        mocked_flow_class,
        mocked_auth_service_class,
        mocked_set_refresh_cookie,
    ):
        user = CustomUser.objects.create_user(
            email="existing@example.com",
            name="Existing User",
            password="password123",
            google_id="google-existing-1",
        )
        mocked_flow = mocked_flow_class.return_value
        mocked_flow.get_tokens.return_value = SimpleNamespace(refresh_token=None)
        mocked_flow.get_user_info.return_value = SimpleNamespace(
            sub="google-existing-1",
            email="existing@example.com",
            name="Existing User",
            picture=None,
        )

        mocked_auth_service = mocked_auth_service_class.return_value
        mocked_auth_service.authenticate_user.return_value = (
            {"access_token": "access-jwt", "refresh_token": "refresh-jwt"},
            user,
            False,
        )
        mocked_set_refresh_cookie.side_effect = lambda response, refresh_token: response

        url = reverse("google_auth:google_callback")
        response = self.client.post(
            url,
            {"code": "mock-code", "state": "mock-state"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["access_jwt"], "access-jwt")
        self.assertFalse(response.data["created"])
        mocked_set_refresh_cookie.assert_called_once()

    @patch("google_auth.apis.GoogleCalendarService")
    @patch("google_auth.apis.AuthService")
    @patch("google_auth.apis.GoogleRawLoginFlowService")
    def test_google_callback_returns_403_if_created_without_google_refresh_token(
        self,
        mocked_flow_class,
        mocked_auth_service_class,
        mocked_calendar_service_class,
    ):
        user = CustomUser.objects.create_user(
            email="new@example.com",
            name="New User",
            password="password123",
            google_id="google-new-1",
        )
        mocked_flow = mocked_flow_class.return_value
        mocked_flow.get_tokens.return_value = SimpleNamespace(refresh_token=None)
        mocked_flow.get_user_info.return_value = SimpleNamespace(
            sub="google-new-1",
            email="new@example.com",
            name="New User",
            picture=None,
        )

        mocked_auth_service = mocked_auth_service_class.return_value
        mocked_auth_service.authenticate_user.return_value = (
            {"access_token": "access-jwt", "refresh_token": "refresh-jwt"},
            user,
            True,
        )

        url = reverse("google_auth:google_callback")
        response = self.client.post(
            url,
            {"code": "mock-code", "state": "mock-state"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mocked_calendar_service_class.return_value.create_user_calendars.assert_called_once_with(
            user=user
        )


class GoogleAuthServicesTests(TestCase):
    def setUp(self):
        cache.clear()
        caches[settings.GOOGLE_AUTH_TOKEN_CACHE_ALIAS].clear()

    def test_set_refresh_cookie_sets_cookie(self):
        response = HttpResponse()
        updated = set_refresh_cookie(response, "refresh-token-value")

        self.assertIs(updated, response)
        self.assertIn("refresh_jwt", updated.cookies)
        self.assertEqual(updated.cookies["refresh_jwt"].value, "refresh-token-value")

    def test_store_user_token_and_get_user_token_roundtrip(self):
        store_user_token(user_id="google-user-1", token="token-123", expires_in=120)
        token = get_user_token("google-user-1")

        self.assertEqual(token, "token-123")

    def test_save_google_refresh_token_creates_row(self):
        user = CustomUser.objects.create_user(
            email="refresh@example.com",
            name="Refresh User",
            password="password123",
            google_id="google-refresh-1",
        )
        save_google_refresh_token(user=user, refresh_token="google-refresh-token")

        stored = GoogleRefreshToken.objects.get(user=user)
        self.assertEqual(stored.refresh_token, "google-refresh-token")

    @patch("google_auth.services.Credentials.from_authorized_user_info")
    def test_get_user_credentials_builds_credentials_from_stored_tokens(
        self, mocked_from_authorized_user_info
    ):
        user = CustomUser.objects.create_user(
            email="creds@example.com",
            name="Creds User",
            password="password123",
            google_id="google-creds-1",
        )
        GoogleRefreshToken.objects.create(user=user, refresh_token="refresh-token")
        store_user_token(user.google_id, "cached-access-token", expires_in=120)

        fake_creds = SimpleNamespace(
            expired=False,
            refresh_token="refresh-token",
            token="cached-access-token",
        )
        mocked_from_authorized_user_info.return_value = fake_creds

        creds = get_user_credentials(user.google_id)

        self.assertIs(creds, fake_creds)
        mocked_from_authorized_user_info.assert_called_once()
