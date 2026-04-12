# events/services.py
import re
import requests
from datetime import datetime, time
from google_auth.services import get_user_credentials
from core.exceptions import EventNotFoundError, GoogleNetworkError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from .models import Event, UserCalendar
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from .serializers import GoogleCalendarEventSerializer, UserCalendarSerializer
import logging
from rest_framework.exceptions import ValidationError

from core.exceptions import CalendarCreationError, CalendarSyncError
from core.enums import EmbeddingStatus
from .tasks import generate_event_embedding

logger = logging.getLogger(__name__)

# IANA timezone format (e.g. Europe/Moscow) — для валидации timezone из Google Calendar
IANA_TIMEZONE_RE = re.compile(r"^[A-Za-z]+(?:[._-][A-Za-z0-9]+)*(?:/[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*)+$")


class GoogleCalendarService:
    CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"

    # TODO: проверить работу
    def __init__(self):
        self._credentials = None

    def _get_credentials(self, user):
        if not self._credentials:
            self._credentials = get_user_credentials(user.google_id)
        return self._credentials

    def _build_google_service(self, user):
        credentials = self._get_credentials(user)
        service = build('calendar', 'v3', credentials=credentials)
        return service

    def _get_headers(self, access_token):
        """
        Формируем заголовки для запроса с переданным access_token.
        """
        return {
            "Authorization": f"Bearer {access_token}",
        }

    def get_google_calendars(self, user):
        """
        Получает список календарей, доступных для пользователя.
        Возвращает список словарей, содержащих информацию о календарях,
        включая id, summary, description, timezone и primary.
        
        :param user: пользователь, для которого нужно получить список календарей
        :raises GoogleNetworkError: если возникла ошибка при работе с Google API
        :raises Exception: если возникла любая другая ошибка
        """
        try:
            service = self._build_google_service(user)
            calendar_list = service.calendarList().list().execute()
            
            return [
            {
                "google_calendar_id": calendar.get("id"),
                "summary": calendar.get("summary"),
                "description": calendar.get("description", None),
                "time_zone": calendar.get("timeZone", None),
                "primary": calendar.get("primary", 'false'),
                'background_color': calendar.get("backgroundColor"),
                # 'foregroundColor': calendar.get("foregroundColor"),
                "owner": calendar.get("accessRole", False) == 'owner',
                "primary": calendar.get("primary", 'false'),
            }
            for calendar in calendar_list.get("items", [])
            ]

        except HttpError as e:
            raise GoogleNetworkError(f"Ошибка при обращении к Google API: {str(e)}")

    def _set_user_timezone_from_primary_calendar(self, user, calendars):
        if user.time_zone:
            return
        primary_cal = next(
            (c for c in calendars if c.get("primary") in (True, "true")),
            None,
        )
        if not primary_cal:
            return
        tz = primary_cal.get("time_zone")
        if tz and isinstance(tz, str) and IANA_TIMEZONE_RE.match(tz.strip()):
            user.time_zone = tz.strip()
            user.save(update_fields=["time_zone"])
            logger.info(
                "Set user %s timezone from primary calendar: %s",
                user.email,
                user.time_zone,
            )

    def create_user_calendars(self, user):
        """
        Создает календари пользователя в базе данных.
        При первом создании профиля устанавливает timezone пользователя из primary-календаря,
        т.к. Google userinfo не возвращает timezone.
        """
        try:
            calendars = self.get_google_calendars(user)
            self._set_user_timezone_from_primary_calendar(user, calendars)
            serializer = UserCalendarSerializer(data=calendars, many=True)
            if serializer.is_valid():
                user_calendars = [UserCalendar(**data, user=user) for data in serializer.validated_data]
                UserCalendar.objects.bulk_create(user_calendars)
            else:
                raise CalendarCreationError(f"Ошибка сериализации календарей: {serializer.errors}")
        except CalendarSyncError as e:
            raise CalendarSyncError(f"Ошибка синхронизации календарей для пользователя {user}: {e}")

    def sync_user_calendars_safely(self, user):
        """
        Безопасно обновляет календари пользователя без удаления записей,
        чтобы не триггерить каскадное удаление Task/Event.
        """
        calendars = self.get_google_calendars(user)
        self._set_user_timezone_from_primary_calendar(user, calendars)

        serializer = UserCalendarSerializer(data=calendars, many=True)
        if not serializer.is_valid():
            raise CalendarCreationError(f"Ошибка сериализации календарей: {serializer.errors}")

        validated_calendars = serializer.validated_data
        existing_calendars = {
            calendar.google_calendar_id: calendar
            for calendar in UserCalendar.objects.filter(user=user)
        }
        fetched_google_calendar_ids = set()
        to_create = []
        to_update = []

        for calendar_data in validated_calendars:
            google_calendar_id = calendar_data["google_calendar_id"]
            fetched_google_calendar_ids.add(google_calendar_id)
            existing = existing_calendars.get(google_calendar_id)

            if not existing:
                to_create.append(UserCalendar(user=user, **calendar_data))
                continue

            changed = False
            for field in ("summary", "description", "owner", "background_color", "time_zone", "primary"):
                new_value = calendar_data.get(field)
                if getattr(existing, field) != new_value:
                    setattr(existing, field, new_value)
                    changed = True
            if existing.primary and not existing.selected:
                existing.selected = True
                changed = True
            if changed:
                to_update.append(existing)

        with transaction.atomic():
            if to_create:
                UserCalendar.objects.bulk_create(to_create)
            if to_update:
                UserCalendar.objects.bulk_update(
                    to_update,
                    ["summary", "description", "owner", "background_color", "time_zone", "primary", "selected"],
                )
            if fetched_google_calendar_ids:
                UserCalendar.objects.filter(user=user).exclude(
                    google_calendar_id__in=fetched_google_calendar_ids
                ).update(selected=False)

        return UserCalendar.objects.filter(user=user)
        
    def toggle_calendar_select(self, user, google_calendar_id):
        """
        Переключает выбор календарей для пользователя.
        """
        try:
            calendar = UserCalendar.objects.get(user=user, google_calendar_id=google_calendar_id)
            if calendar.primary and calendar.selected:
                raise ValidationError("Нельзя отключить основной календарь")
            calendar.selected = not calendar.selected
            calendar.save()
            return calendar.selected
        except UserCalendar.DoesNotExist:
            raise CalendarSyncError(f"Календарь {google_calendar_id} не найден")

    def get_events_from_calendar(self, calendar, credentials, time_min, time_max):
        """
        Получает события из календаря пользователя в заданном диапазоне времени.
        """
        try:
            access_token = credentials.token
            headers = self._get_headers(access_token)
            url = self.CALENDAR_EVENTS_URL.format(calendar_id=calendar.google_calendar_id)
            params = {
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": True,
                "orderBy": "startTime"
            }
            response = requests.get(url, headers=headers, params=params)

            if not response.ok:
                raise GoogleNetworkError(f"Ошибка при получении событий: {response.status_code}")
            payload = response.json()

            return payload
        except GoogleNetworkError as e:
            raise GoogleNetworkError(f"Ошибка при получении событий из календаря {calendar.google_calendar_id}: {str(e)}")
        except Exception as e:
            raise CalendarSyncError(f"Неизвестная ошибка при получении событий из календаря {calendar.google_calendar_id}: {str(e)}")

    def get_all_events(self, user, time_min, time_max):
        """
        Получает события для всех выбранных календарей пользователя.
        Возвращает (список событий, id календарей UserCalendar, для которых ответ Google получен успешно).

        Для календарей с ошибкой API id не попадает во второй компонент — чтобы синхронизация
        не удаляла локальные события.
        """
        user_calendars = UserCalendar.objects.filter(user=user, selected=True)
        events_list = []
        fetched_calendar_ids: set[int] = set()
        credentials = self._get_credentials(user)
        for calendar in user_calendars:
            try:
                calendar_events = self.get_events_from_calendar(calendar, credentials, time_min, time_max)
                fetched_calendar_ids.add(calendar.id)
                raw_events = calendar_events.get("items", [])
                for event in raw_events:
                    event['user_calendar_id'] = calendar.id
                    serializer = GoogleCalendarEventSerializer(data=event)
                    if serializer.is_valid():
                        events_list.append(serializer.data)
                    else:
                        logger.error("Failed to serialize event: %s", event, serializer.errors)

            except Exception as e:
                logger.error("Failed to get events from calendar %s: %s", calendar.google_calendar_id, str(e))

        return events_list, fetched_calendar_ids

    def _extract_event_datetimes(self, event_data):
        start_payload = event_data.get("start") or {}
        end_payload = event_data.get("end") or {}

        start_raw = start_payload.get("dateTime") or start_payload.get("date")
        end_raw = end_payload.get("dateTime") or end_payload.get("date")

        start_dt = parse_datetime(start_raw) if start_raw else None
        end_dt = parse_datetime(end_raw) if end_raw else None

        if start_dt and timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt)
        if end_dt and timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt)

        if not start_dt and start_raw:
            parsed_start_date = parse_date(start_raw)
            if parsed_start_date:
                start_dt = timezone.make_aware(datetime.combine(parsed_start_date, time.min))

        if not end_dt and end_raw:
            parsed_end_date = parse_date(end_raw)
            if parsed_end_date:
                end_dt = timezone.make_aware(datetime.combine(parsed_end_date, time.min))

        return start_dt, end_dt

    def upsert_local_event(
        self,
        *,
        user_calendar: UserCalendar,
        event_data: dict,
        task_id: int | None = None,
        start_dt=None,
        end_dt=None,
        enqueue_embedding: bool = True,
    ) -> Event:
        from tasks.models import Task

        start_value = start_dt
        end_value = end_dt
        if start_value is None and end_value is None:
            start_value, end_value = self._extract_event_datetimes(event_data)

        organizer_email = (
            (event_data.get("organizer") or {}).get("email")
            or event_data.get("organizer_email")
        )
        incoming_summary = event_data.get("summary")
        incoming_description = event_data.get("description")
        existing = Event.objects.filter(
            user_calendar=user_calendar,
            google_event_id=event_data.get("id"),
        ).first()
        text_fields_changed = (
            existing is None
            or existing.summary != incoming_summary
            or existing.description != incoming_description
        )

        defaults = {
            "summary": incoming_summary,
            "description": incoming_description,
            "start": start_value,
            "end": end_value,
            "htmlLink": event_data.get("htmlLink"),
            "organizer_email": organizer_email,
        }
        if text_fields_changed and enqueue_embedding:
            defaults["embedding_status"] = EmbeddingStatus.PENDING
        if task_id is not None:
            parsed_task_id = None
            try:
                parsed_task_id = int(task_id)
            except (TypeError, ValueError):
                parsed_task_id = None

            if parsed_task_id and Task.objects.filter(id=parsed_task_id).exists():
                defaults["task_id"] = parsed_task_id
            else:
                defaults["task_id"] = None

        local_event, _ = Event.objects.update_or_create(
            user_calendar=user_calendar,
            google_event_id=event_data.get("id"),
            defaults=defaults,
        )
        if text_fields_changed and enqueue_embedding:
            generate_event_embedding.delay(local_event.id)
        return local_event

    def sync_events_for_user(self, user, time_min, time_max):
        user_calendars = UserCalendar.objects.filter(user=user, selected=True)
        events_payload, fetched_calendar_ids = self.get_all_events(user, time_min, time_max)
        sync_start = parse_datetime(time_min)
        sync_end = parse_datetime(time_max)

        if not user_calendars.exists():
            return []

        calendar_ids = list(user_calendars.values_list("id", flat=True))
        existing_events = Event.objects.filter(
            user_calendar_id__in=calendar_ids,
            start__gte=sync_start,
            start__lte=sync_end,
        )
        existing_by_key = {
            (event.user_calendar_id, event.google_event_id): event
            for event in existing_events
            if event.google_event_id
        }

        seen_google_ids_by_calendar = {calendar_id: set() for calendar_id in calendar_ids}
        to_create = []
        to_update = []
        to_reembed = []

        for event_data in events_payload:
            calendar_id = event_data.get("user_calendar_id")
            google_event_id = event_data.get("id")
            if not calendar_id or not google_event_id:
                continue

            seen_google_ids_by_calendar.setdefault(calendar_id, set()).add(google_event_id)
            start_dt, end_dt = self._extract_event_datetimes(event_data)
            organizer_email = (
                event_data.get("organizer_email")
                or (event_data.get("organizer") or {}).get("email")
            )

            event_values = {
                "summary": event_data.get("summary"),
                "description": event_data.get("description"),
                "start": start_dt,
                "end": end_dt,
                "htmlLink": event_data.get("htmlLink"),
                "organizer_email": organizer_email,
            }

            existing = existing_by_key.get((calendar_id, google_event_id))
            if existing:
                changed = False
                text_fields_changed = (
                    existing.summary != event_values["summary"]
                    or existing.description != event_values["description"]
                )
                for field, value in event_values.items():
                    if getattr(existing, field) != value:
                        setattr(existing, field, value)
                        changed = True
                if changed:
                    if text_fields_changed:
                        existing.embedding_status = EmbeddingStatus.PENDING
                        to_reembed.append(existing)
                    to_update.append(existing)
            else:
                to_create.append(
                    Event(
                        user_calendar_id=calendar_id,
                        google_event_id=google_event_id,
                        embedding_status=EmbeddingStatus.PENDING,
                        **event_values,
                    )
                )

        with transaction.atomic():
            if to_create:
                Event.objects.bulk_create(to_create)
            if to_update:
                Event.objects.bulk_update(
                    to_update,
                    ["summary", "description", "start", "end", "htmlLink", "organizer_email", "embedding_status"],
                )

            # Удаляем только то, что точно отсутствует в успешно полученном снимке Google
            # (при ошибке API для календаря fetched_calendar_ids его не содержит — локальные события сохраняем)
            for calendar_id in calendar_ids:
                if calendar_id not in fetched_calendar_ids:
                    continue
                seen_google_ids = seen_google_ids_by_calendar.get(calendar_id, set())
                if seen_google_ids:
                    Event.objects.filter(
                        user_calendar_id=calendar_id,
                        start__gte=sync_start,
                        start__lte=sync_end,
                    ).exclude(
                        google_event_id__in=seen_google_ids
                    ).delete()
                else:
                    Event.objects.filter(
                        user_calendar_id=calendar_id,
                        start__gte=sync_start,
                        start__lte=sync_end,
                    ).delete()

        for event in to_create:
            generate_event_embedding.delay(event.id)
        for event in to_reembed:
            generate_event_embedding.delay(event.id)

        return events_payload

    def create_event(self, user, google_calendar_id, event_data):
        """
        Создает событие в календаре пользователя.
        :param google_calendar_id: Google calendar ID (строка)
        """
        try:
            service = self._build_google_service(user)
            event = service.events().insert(calendarId=google_calendar_id, body=event_data).execute()
            return event
        except HttpError as e:
            raise EventNotFoundError(f"Ошибка при создании события: {str(e)}")

    def update_event(self, user, google_calendar_id, event_id, event_data):
        """
        Обновляет существующее событие в календаре пользователя.
        :param google_calendar_id: Google calendar ID (строка)
        """
        try:
            service = self._build_google_service(user)
            patched = service.events().patch(
                calendarId=google_calendar_id, 
                eventId=event_id, 
                body=event_data
            ).execute()
            return patched
        except HttpError as e:
            raise EventNotFoundError(f"Ошибка при обновлении события: {str(e)}")

    def delete_event(self, user, google_calendar_id, event_id):
        """
        Удаляет событие из календаря пользователя.
        :param google_calendar_id: Google calendar ID (строка)
        """
        try:
            service = self._build_google_service(user)
            service.events().delete(calendarId=google_calendar_id, eventId=event_id).execute()
        except HttpError as e:
            raise EventNotFoundError(f"Ошибка при удалении события: {str(e)}")

def add_event_extended_properties(event: dict, task_id: int | None = None):
    """
    Добавляет расширенные свойства событию.
    "chronika__object-type": 1 - задача, 0 - событие 
    """
    if task_id:
        event['extendedProperties'] = {
            'private': {
                "chronika__touched": True,
                "chronika__object-type": 1,
                "chronika__task-id": task_id,
            }
    }
    else:
        event['extendedProperties'] = {
            'private': {
                "chronika__touched": True,
                "chronika__object-type": 0,
            }
        }

    return event

# Сырой объект события
# {
#     "kind": "calendar#event",
#     "etag": "\"3477214580834000\"",
#     "id": "545o03qe1mi3ac2qd06i0p26md",
#     "status": "confirmed",
#     "htmlLink": "https://www.google.com/calendar/event?eid=NTQ1bzAzcWUxbWkzYWMycWQwNmkwcDI2bWQgNzNhcjlmaHU4bHU4aXNuMmhxdnZvMTk5aDhAZw",
#     "created": "2025-02-03T18:28:10.000Z",
#     "updated": "2025-02-03T18:28:10.417Z",
#     "summary": "на ломоносовскую",
#     "creator": {
#         "email": "daryaami10@gmail.com"
#     },
#     "organizer": {
#         "email": "73ar9fhu8lu8isn2hqvvo199h8@group.calendar.google.com",
#         "displayName": "В дороге",
#         "self": true
#     },
#     "start": {
#         "dateTime": "2025-02-05T11:00:00+03:00",
#         "timeZone": "Europe/Moscow"
#     },
#     "end": {
#         "dateTime": "2025-02-05T12:30:00+03:00",
#         "timeZone": "Europe/Moscow"
#     },
#     "iCalUID": "545o03qe1mi3ac2qd06i0p26md@google.com",
#     "sequence": 0,
#     "guestsCanInviteOthers": false,
#     "reminders": {
#         "useDefault": true
#     },
#     "eventType": "default",
#     "calendar": "73ar9fhu8lu8isn2hqvvo199h8@group.calendar.google.com",
#     "extendedProperties": {
#         "private": {
#             "chronika__touched": true,
#             "chronika__object-type": 1,
#             "chronika__task-id": "42",
#         },
#     }

# }