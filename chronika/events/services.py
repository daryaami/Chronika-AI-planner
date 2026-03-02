# events/services.py
import requests
from google_auth.services import get_user_credentials
from core.exceptions import EventNotFoundError, GoogleNetworkError
from .models import UserCalendar
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from .serializers import GoogleCalendarEventSerializer, UserCalendarSerializer
import logging
from core.exceptions import CalendarCreationError, CalendarSyncError

logger = logging.getLogger(__name__)


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

    def create_user_calendars(self, user):
        """
        Создает календари пользователя в базе данных.
        """
        try:
            calendars = self.get_google_calendars(user)
            serializer = UserCalendarSerializer(data=calendars, many=True)
            if serializer.is_valid():
                user_calendars = [UserCalendar(**data, user=user) for data in serializer.validated_data]
                UserCalendar.objects.bulk_create(user_calendars)
            else:
                raise CalendarCreationError(f"Ошибка сериализации календарей: {serializer.errors}")
        except CalendarSyncError as e:
            raise CalendarSyncError(f"Ошибка синхронизации календарей для пользователя {user}: {e}")
        
    def toggle_calendar_select(self, user, google_calendar_id):
        """
        Переключает выбор календарей для пользователя.
        """
        try:
            calendar = UserCalendar.objects.get(user=user, google_calendar_id=google_calendar_id)
            if calendar.primary and calendar.selected:
                raise CalendarSyncError("Нельзя отключить основной календарь")
            calendar.selected = not calendar.selected
            calendar.save()
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

            return response.json()
        except GoogleNetworkError as e:
            raise GoogleNetworkError(f"Ошибка при получении событий из календаря {calendar.google_calendar_id}: {str(e)}")
        except Exception as e:
            raise CalendarSyncError(f"Неизвестная ошибка при получении событий из календаря {calendar.google_calendar_id}: {str(e)}")

    def get_all_events(self, user, time_min, time_max):
        """
        Получает события для всех выбранных календарей пользователя.
        Возвращает список событий, где каждое событие дополнено информацией о календаре.
        """
        user_calendars = UserCalendar.objects.filter(user=user, selected=True)
        events_list = []
        credentials = self._get_credentials(user)
        for calendar in user_calendars:
            try:
                calendar_events = self.get_events_from_calendar(calendar, credentials, time_min, time_max)
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

        return events_list

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

def add_event_extended_properties(event: dict, task_id: int | None = None, timelog_id: int | None = None):
    """
    Добавляет расширенные свойства событию.
    "chronika__object-type": 1 - задача, 0 - событие 
    """
    if task_id: #and timelog_id:
        event['extendedProperties'] = {
            'private': {
                "chronika__touched": True,
                "chronika__object-type": 1,
                "chronika__task-id": task_id,
                # "chronika__connected-timelog-id": timelog_id,
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
    # "extendedProperties": {
        # "private": {
        #     "chronika__touched": true,
        #     "chronika__object-type": 1,
        #     "chronika__task-id": "42",
        #     "chronika__connected-timelog-id": "42",
        # },
    
    # }

# }