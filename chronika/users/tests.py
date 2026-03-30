from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import CustomUser


class UsersApiTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="profile@example.com",
            name="Profile User",
            password="password123",
            google_id="google-profile-1",
        )
        self.client.force_authenticate(self.user)

    def test_profile_patch_updates_name_and_timezone(self):
        url = reverse("profile")
        response = self.client.patch(
            url,
            {"name": "Updated Name", "time_zone": "Europe/Moscow"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "Updated Name")
        self.assertEqual(self.user.time_zone, "Europe/Moscow")

    def test_profile_patch_rejects_invalid_timezone(self):
        url = reverse("profile")
        response = self.client.patch(url, {"time_zone": "Not/A Real TZ"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_refresh_requires_refresh_cookie(self):
        url = reverse("token_refresh")
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_profile_get_returns_current_user(self):
        url = reverse("profile")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)

    def test_logout_clears_cookie_and_returns_204(self):
        url = reverse("logout")
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIn("refresh_jwt", response.cookies)
        self.assertEqual(response.cookies["refresh_jwt"].value, "")

    def test_profile_delete_deletes_user(self):
        url = reverse("profile")
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CustomUser.objects.filter(id=self.user.id).exists())

    def test_token_ping_returns_200_with_valid_tokens(self):
        refresh = RefreshToken.for_user(self.user)
        access = str(refresh.access_token)

        url = reverse("ping")
        self.client.cookies["refresh_jwt"] = str(refresh)
        response = self.client.get(url, HTTP_AUTHORIZATION=f"JWT {access}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Tokens are valid.")
