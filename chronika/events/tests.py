from datetime import datetime
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from events.models import Event, UserCalendar
from events.services import GoogleCalendarService
from core.exceptions import GoogleRefreshTokenError


def _recreate_user_calendars_after_sync(user):
    """Имитация create_user_calendars после delete в update endpoint."""
    UserCalendar.objects.create(
        user=user,
        google_calendar_id="selected-cal-id",
        summary="Selected calendar",
        selected=True,
        owner=True,
        primary=True,
    )
    UserCalendar.objects.create(
        user=user,
        google_calendar_id="unselected-cal-id",
        summary="Unselected calendar",
        selected=False,
        owner=True,
        primary=False,
    )
    UserCalendar.objects.create(
        user=user,
        google_calendar_id="extra-cal-id",
        summary="Extra calendar",
        selected=True,
        owner=True,
        primary=False,
    )
from tasks.models import Task
from users.models import CustomUser


class EventEndpointsTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="test@example.com",
            name="Test User",
            password="password123",
            google_id="google-user-1",
        )
        self.client.force_authenticate(self.user)

        self.selected_calendar = UserCalendar.objects.create(
            user=self.user,
            google_calendar_id="selected-cal-id",
            summary="Selected calendar",
            selected=True,
            owner=True,
            primary=True,
        )
        self.unselected_calendar = UserCalendar.objects.create(
            user=self.user,
            google_calendar_id="unselected-cal-id",
            summary="Unselected calendar",
            selected=False,
            owner=True,
            primary=False,
        )

    def _aware_dt(self, year, month, day, hour=10, minute=0):
        return timezone.make_aware(datetime(year, month, day, hour, minute))

    @patch("events.services.GoogleCalendarService.get_all_events")
    def test_get_events_reads_only_from_db(self, mocked_get_all_events):
        Event.objects.create(
            user_calendar=self.selected_calendar,
            google_event_id="evt-selected-in-range",
            summary="Selected in range",
            start=self._aware_dt(2026, 3, 10),
            end=self._aware_dt(2026, 3, 10, 11, 0),
        )
        Event.objects.create(
            user_calendar=self.unselected_calendar,
            google_event_id="evt-unselected-in-range",
            summary="Unselected in range",
            start=self._aware_dt(2026, 3, 11),
            end=self._aware_dt(2026, 3, 11, 11, 0),
        )
        Event.objects.create(
            user_calendar=self.selected_calendar,
            google_event_id="evt-selected-out-range",
            summary="Selected out range",
            start=self._aware_dt(2026, 4, 2),
            end=self._aware_dt(2026, 4, 2, 11, 0),
        )

        url = reverse("calendar_events")
        response = self.client.get(url, {"start": "2026-03-01", "end": "2026-03-31"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], "evt-selected-in-range")
        mocked_get_all_events.assert_not_called()

    @patch("events.services.generate_event_embedding.delay")
    @patch(
        "events.services.GoogleCalendarService.get_all_events",
        return_value=[
            {
                "id": "google-new-event",
                "summary": "Synced event",
                "description": "From Google",
                "start": {"dateTime": "2026-03-15T10:00:00+00:00"},
                "end": {"dateTime": "2026-03-15T11:00:00+00:00"},
                "htmlLink": "https://google.com/event/new",
                "organizer_email": "organizer@example.com",
                "user_calendar_id": 0,  # replaced in test
            }
        ],
    )
    def test_sync_endpoint_syncs_then_returns_events_from_db(self, mocked_get_all_events, mocked_delay):
        payload = mocked_get_all_events.return_value
        payload[0]["user_calendar_id"] = self.selected_calendar.id

        url = reverse("sync_calendar_events")
        response = self.client.post(f"{url}?start=2026-03-01&end=2026-03-31")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], "google-new-event")
        self.assertTrue(Event.objects.filter(google_event_id="google-new-event").exists())
        mocked_get_all_events.assert_called_once()
        self.assertTrue(mocked_delay.called)

    @patch("events.services.generate_event_embedding.delay")
    @patch("events.services.GoogleCalendarService.get_all_events", return_value=[])
    def test_sync_endpoint_deletes_missing_events_only_in_range(self, _, mocked_delay):
        Event.objects.create(
            user_calendar=self.selected_calendar,
            google_event_id="in-range-event",
            summary="To be removed",
            start=self._aware_dt(2026, 3, 12),
            end=self._aware_dt(2026, 3, 12, 13, 0),
        )
        Event.objects.create(
            user_calendar=self.selected_calendar,
            google_event_id="out-range-event",
            summary="Must stay",
            start=self._aware_dt(2026, 4, 12),
            end=self._aware_dt(2026, 4, 12, 13, 0),
        )

        url = reverse("sync_calendar_events")
        response = self.client.post(f"{url}?start=2026-03-01&end=2026-03-31")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Event.objects.filter(google_event_id="in-range-event").exists())
        self.assertTrue(Event.objects.filter(google_event_id="out-range-event").exists())
        mocked_delay.assert_not_called()

    @patch("events.services.GoogleCalendarService.get_events_from_calendar")
    @patch("events.services.GoogleCalendarService._get_credentials")
    def test_get_all_events_preserves_organizer_email_from_google_payload(
        self, mocked_get_credentials, mocked_get_events_from_calendar
    ):
        mocked_get_credentials.return_value = object()
        mocked_get_events_from_calendar.return_value = {
            "items": [
                {
                    "id": "google-event-1",
                    "summary": "Synced from Google",
                    "start": {"dateTime": "2026-03-15T10:00:00+00:00"},
                    "end": {"dateTime": "2026-03-15T11:00:00+00:00"},
                    "organizer": {"email": "owner@example.com"},
                }
            ]
        }

        service = GoogleCalendarService()
        events = service.get_all_events(
            self.user,
            "2026-03-01T00:00:00+00:00",
            "2026-03-31T23:59:59+00:00",
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["organizer_email"], "owner@example.com")
        self.assertEqual(events[0]["user_calendar_id"], self.selected_calendar.id)

    def test_get_calendars_returns_user_calendars(self):
        url = reverse("google_calendars_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    @patch("events.apis.GoogleCalendarService.toggle_calendar_select", return_value=True)
    def test_toggle_calendar_select_endpoint(self, mocked_toggle):
        url = reverse("toggle_calendar_select")
        response = self.client.post(
            url,
            {"google_calendar_id": self.unselected_calendar.google_calendar_id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["selected"])
        mocked_toggle.assert_called_once_with(
            self.user, self.unselected_calendar.google_calendar_id
        )

    def test_toggle_primary_calendar_forbidden(self):
        url = reverse("toggle_calendar_select")
        response = self.client.post(
            url,
            {"google_calendar_id": self.selected_calendar.google_calendar_id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.selected_calendar.refresh_from_db()
        self.assertTrue(self.selected_calendar.selected)

    @patch(
        "events.apis.GoogleCalendarService.create_user_calendars",
        side_effect=_recreate_user_calendars_after_sync,
    )
    def test_update_calendars_recreates_and_applies_selected_states(self, mocked_create):
        url = reverse("update_calendar")
        response = self.client.post(
            url,
            [
                {"google_calendar_id": "extra-cal-id", "selected": False},
                {
                    "google_calendar_id": self.unselected_calendar.google_calendar_id,
                    "selected": True,
                },
            ],
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mocked_create.assert_called_once_with(self.user)
        extra = UserCalendar.objects.get(
            user=self.user, google_calendar_id="extra-cal-id"
        )
        unselected = UserCalendar.objects.get(
            user=self.user, google_calendar_id=self.unselected_calendar.google_calendar_id
        )
        self.assertFalse(extra.selected)
        self.assertTrue(unselected.selected)

    @patch(
        "events.apis.GoogleCalendarService.create_user_calendars",
        side_effect=_recreate_user_calendars_after_sync,
    )
    def test_update_calendars_cannot_disable_primary(self, mocked_create):
        url = reverse("update_calendar")
        response = self.client.post(
            url,
            [
                {
                    "google_calendar_id": self.selected_calendar.google_calendar_id,
                    "selected": False,
                },
            ],
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("events.services.generate_event_embedding.delay")
    @patch("events.apis.GoogleCalendarService.create_event")
    def test_create_event_endpoint_saves_event_in_db(self, mocked_create_event, mocked_delay):
        mocked_create_event.return_value = {
            "id": "created-evt-1",
            "summary": "Created event",
            "description": "Created description",
            "start": {"dateTime": "2026-03-20T10:00:00+00:00"},
            "end": {"dateTime": "2026-03-20T11:00:00+00:00"},
            "htmlLink": "https://google.com/event/created",
            "organizer": {"email": "org@example.com"},
        }
        url = reverse("calendar_events")
        response = self.client.post(
            url,
            {
                "summary": "Created event",
                "user_calendar_id": self.selected_calendar.id,
                "start": {"dateTime": "2026-03-20T10:00:00+00:00"},
                "end": {"dateTime": "2026-03-20T11:00:00+00:00"},
                "description": "Created description",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Event.objects.get(google_event_id="created-evt-1")
        self.assertEqual(created.embedding_status, "PENDING")
        mocked_delay.assert_called_once_with(created.id)

    @patch("events.services.generate_event_embedding.delay")
    @patch("events.apis.GoogleCalendarService.update_event")
    def test_update_event_endpoint_updates_local_event(self, mocked_update_event, mocked_delay):
        Event.objects.create(
            user_calendar=self.selected_calendar,
            google_event_id="evt-1",
            summary="Old",
            start=self._aware_dt(2026, 3, 20),
            end=self._aware_dt(2026, 3, 20, 11, 0),
        )
        mocked_update_event.return_value = {
            "id": "evt-1",
            "summary": "Updated",
            "description": "Updated description",
            "start": {"dateTime": "2026-03-20T12:00:00+00:00"},
            "end": {"dateTime": "2026-03-20T13:00:00+00:00"},
            "htmlLink": "https://google.com/event/evt-1",
            "organizer": {"email": "org@example.com"},
        }
        url = reverse("calendar_events")
        response = self.client.put(
            url,
            {
                "event_id": "evt-1",
                "user_calendar_id": self.selected_calendar.id,
                "summary": "Updated",
                "start": {"dateTime": "2026-03-20T12:00:00+00:00"},
                "end": {"dateTime": "2026-03-20T13:00:00+00:00"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated = Event.objects.get(user_calendar=self.selected_calendar, google_event_id="evt-1")
        self.assertEqual(updated.summary, "Updated")
        self.assertEqual(updated.embedding_status, "PENDING")
        mocked_delay.assert_called_once_with(updated.id)

    @patch("events.services.generate_event_embedding.delay")
    @patch("events.apis.GoogleCalendarService.update_event")
    def test_update_event_endpoint_does_not_enqueue_when_only_non_text_fields_change(
        self,
        mocked_update_event,
        mocked_delay,
    ):
        Event.objects.create(
            user_calendar=self.selected_calendar,
            google_event_id="evt-no-text-change",
            summary="Same summary",
            description="Same description",
            start=self._aware_dt(2026, 3, 20),
            end=self._aware_dt(2026, 3, 20, 11, 0),
            embedding_status="COMPLETED",
        )
        mocked_update_event.return_value = {
            "id": "evt-no-text-change",
            "summary": "Same summary",
            "description": "Same description",
            "start": {"dateTime": "2026-03-20T12:00:00+00:00"},
            "end": {"dateTime": "2026-03-20T13:00:00+00:00"},
            "htmlLink": "https://google.com/event/evt-no-text-change",
            "organizer": {"email": "org@example.com"},
        }

        url = reverse("calendar_events")
        response = self.client.put(
            url,
            {
                "event_id": "evt-no-text-change",
                "user_calendar_id": self.selected_calendar.id,
                "start": {"dateTime": "2026-03-20T12:00:00+00:00"},
                "end": {"dateTime": "2026-03-20T13:00:00+00:00"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated = Event.objects.get(
            user_calendar=self.selected_calendar,
            google_event_id="evt-no-text-change",
        )
        self.assertEqual(updated.embedding_status, "COMPLETED")
        mocked_delay.assert_not_called()

    @patch("events.apis.GoogleCalendarService.delete_event")
    def test_delete_event_endpoint_removes_local_event(self, mocked_delete_event):
        Event.objects.create(
            user_calendar=self.selected_calendar,
            google_event_id="evt-to-delete",
            summary="To delete",
            start=self._aware_dt(2026, 3, 21),
            end=self._aware_dt(2026, 3, 21, 11, 0),
        )
        url = reverse("calendar_events")
        response = self.client.delete(
            url,
            {
                "event_id": "evt-to-delete",
                "user_calendar_id": self.selected_calendar.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Event.objects.filter(google_event_id="evt-to-delete").exists())
        mocked_delete_event.assert_called_once()

    @patch("events.services.generate_event_embedding.delay")
    @patch("events.apis.GoogleCalendarService.create_event")
    def test_event_from_task_creates_related_event(self, mocked_create_event, mocked_delay):
        task = Task.objects.create(
            user=self.user,
            title="Task title",
            notes="Task notes",
            calendar=self.selected_calendar,
        )
        mocked_create_event.return_value = {
            "id": "from-task-evt",
            "summary": "Task title",
            "description": "Task notes",
            "start": {"dateTime": "2026-03-22T10:00:00+00:00"},
            "end": {"dateTime": "2026-03-22T11:00:00+00:00"},
            "htmlLink": "https://google.com/event/from-task",
            "extendedProperties": {"private": {"chronika__task-id": str(task.id)}},
        }
        url = reverse("event_from_task")
        response = self.client.post(
            url,
            {
                "task_id": task.id,
                "user_calendar_id": self.selected_calendar.id,
                "start": "2026-03-22T10:00:00Z",
                "end": "2026-03-22T11:00:00Z",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Event.objects.get(google_event_id="from-task-evt", task=task)
        self.assertEqual(created.embedding_status, "PENDING")
        mocked_delay.assert_called_once_with(created.id)

    def test_get_events_requires_start_and_end(self):
        url = reverse("calendar_events")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Параметры start и end обязательны")

    def test_get_events_rejects_invalid_date_format(self):
        url = reverse("calendar_events")
        response = self.client.get(url, {"start": "2026/03/01", "end": "2026-03-31"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Неверный формат дат", response.data["error"])

    def test_create_event_with_foreign_calendar_returns_404(self):
        foreign_user = CustomUser.objects.create_user(
            email="foreign@example.com",
            name="Foreign User",
            password="password123",
            google_id="google-foreign-1",
        )
        foreign_calendar = UserCalendar.objects.create(
            user=foreign_user,
            google_calendar_id="foreign-cal",
            summary="Foreign cal",
            selected=True,
            owner=True,
            primary=True,
        )
        url = reverse("calendar_events")
        response = self.client.post(
            url,
            {
                "summary": "Invalid",
                "user_calendar_id": foreign_calendar.id,
                "start": {"dateTime": "2026-03-20T10:00:00+00:00"},
                "end": {"dateTime": "2026-03-20T11:00:00+00:00"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_event_rejects_invalid_payload(self):
        url = reverse("calendar_events")
        response = self.client.post(
            url,
            {
                "summary": "Broken payload",
                "user_calendar_id": self.selected_calendar.id,
                "start": "2026-03-20T10:00:00+00:00",
                "end": {"dateTime": "2026-03-20T11:00:00+00:00"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "validation_error")

    @patch("events.apis.GoogleCalendarService.update_event", side_effect=Exception("boom"))
    def test_update_event_returns_500_when_google_service_fails(self, _):
        url = reverse("calendar_events")
        response = self.client.put(
            url,
            {
                "event_id": "evt-1",
                "user_calendar_id": self.selected_calendar.id,
                "summary": "Updated",
                "start": {"dateTime": "2026-03-20T12:00:00+00:00"},
                "end": {"dateTime": "2026-03-20T13:00:00+00:00"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("Не удалось обновить событие", response.data["error"])

    @patch(
        "events.apis.GoogleCalendarService.sync_events_for_user",
        side_effect=GoogleRefreshTokenError(),
    )
    def test_sync_returns_structured_error_when_service_raises_api_exception(self, _):
        url = reverse("sync_calendar_events")
        response = self.client.post(f"{url}?start=2026-03-01&end=2026-03-31")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "google_refresh_token_error")
