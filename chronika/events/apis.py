# events/api.py
from datetime import datetime, time
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from tasks.models import Task
from .services import GoogleCalendarService, add_event_extended_properties
from core.exceptions import GoogleAuthError, GoogleNetworkError, GoogleRefreshTokenError
from .models import Event, UserCalendar
from .serializers import EventFromTaskSerializer, EventSerializer, GoogleCalendarEventCreateSerializer, GoogleCalendarEventDeleteSerializer, GoogleCalendarEventSerializer, GoogleCalendarEventUpdateSerializer, UserCalendarSerializer
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

def _parse_event_datetime(raw_value):
    if not raw_value:
        return None
    parsed_dt = parse_datetime(raw_value)
    if not parsed_dt:
        return None
    if timezone.is_naive(parsed_dt):
        return timezone.make_aware(parsed_dt)
    return parsed_dt


class UserCalendarEventsApi(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Получить события из локальной БД для активных календарей пользователя",
        manual_parameters=[
            openapi.Parameter('start', openapi.IN_QUERY, description="Дата начала (%Y-%m-%d)", type=openapi.TYPE_STRING),
            openapi.Parameter('end', openapi.IN_QUERY, description="Дата окончания (%Y-%m-%d)", type=openapi.TYPE_STRING),
        ],
        responses={
            200: EventSerializer(many=True),
            400: openapi.Response('Неверный формат дат или отсутствуют параметры start и end', examples={
                'application/json': {"error": "Параметры start и end обязательны"}
            }),
            500: openapi.Response('Ошибка сервера')
        }
    )
    def _get_date_range(self, request):
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        if not start or not end:
            return None, None, Response(
                {"error": "Параметры start и end обязательны"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            start_dt = datetime.combine(datetime.strptime(start, "%Y-%m-%d").date(), time.min)
            end_dt = datetime.combine(datetime.strptime(end, "%Y-%m-%d").date(), time.max)
            start_dt = timezone.make_aware(start_dt)
            end_dt = timezone.make_aware(end_dt)
        except ValueError:
            return None, None, Response(
                {"error": "Неверный формат дат. Ожидается YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return start_dt, end_dt, None

    def _get_events_from_db(self, user, start_dt, end_dt):
        selected_calendar_ids = UserCalendar.objects.filter(
            user=user,
            selected=True,
        ).values_list("id", flat=True)
        events_qs = Event.objects.filter(
            user_calendar_id__in=selected_calendar_ids,
            start__gte=start_dt,
            start__lte=end_dt,
        ).select_related("user_calendar")
        return EventSerializer(events_qs, many=True).data

    def get(self, request, *args, **kwargs):
        """Получить события из локальной БД для активных календарей пользователя"""
        start_dt, end_dt, error_response = self._get_date_range(request)
        if error_response:
            return error_response

        return Response(
            self._get_events_from_db(request.user, start_dt, end_dt),
            status=status.HTTP_200_OK,
        )
        
    @swagger_auto_schema(
        operation_description="Создать новое событие в календаре пользователя",
        request_body=GoogleCalendarEventCreateSerializer,
        responses={
            201: GoogleCalendarEventSerializer,
            400: openapi.Response('Ошибка в данных события'),
        }
    )
    def post(self, request, *args, **kwargs):
        '''Создать новое событие в календаре пользователя'''
        # user_calendar_id = request.data.get('user_calendar_id')
        # event_data = request.data.get('event_data')

        serializer = GoogleCalendarEventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_calendar_id = serializer.validated_data.pop("user_calendar_id")
        event_data = serializer.validated_data

        # Получаем объект UserCalendar по ID из базы данных
        user_calendar = get_object_or_404(UserCalendar, id=user_calendar_id, user=request.user)
        google_calendar_id = user_calendar.google_calendar_id

        calendar_service = GoogleCalendarService()
        event = calendar_service.create_event(request.user, google_calendar_id, event_data)
        calendar_service.upsert_local_event(user_calendar=user_calendar, event_data=event)
        event["user_calendar_id"] = user_calendar.id

        response_serializer = GoogleCalendarEventSerializer(event)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        operation_description="Обновить событие в календаре пользователя",
        request_body=GoogleCalendarEventUpdateSerializer,
        responses={
            200: GoogleCalendarEventSerializer,
            400: openapi.Response('Ошибка в данных события')
        }
    )
    def put(self, request, *args, **kwargs):
        '''Обновить событие в календаре пользователя'''

        serializer = GoogleCalendarEventUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_calendar_id = serializer.validated_data.pop("user_calendar_id")
        event_id = serializer.validated_data.pop("event_id")
        event_data = serializer.validated_data

        # Получаем объект UserCalendar по ID из базы данных
        user_calendar = get_object_or_404(UserCalendar, id=user_calendar_id, user=request.user)
        google_calendar_id = user_calendar.google_calendar_id

        try:
            calendar_service = GoogleCalendarService()
            event = calendar_service.update_event(request.user, google_calendar_id, event_id, event_data)
        except Exception as e:
            return Response({"error": f"Не удалось обновить событие в Google Calendar: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        ext_props = event.get("extendedProperties", {}).get("private", {})
        task_id = ext_props.get("chronika__task-id")
        calendar_service.upsert_local_event(
            user_calendar=user_calendar,
            event_data=event,
            task_id=task_id,
        )
        event["user_calendar_id"] = user_calendar.id

        response_serializer = GoogleCalendarEventSerializer(event)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Удалить событие из календаря пользователя",
        request_body=GoogleCalendarEventDeleteSerializer,
        responses={
            204: openapi.Response('Событие успешно удалено', examples={
                'application/json': {"success": "Событие успешно удалено", "event_deleted": True}
            }),
            400: openapi.Response('Ошибка в параметрах'),
        }
    )
    def delete(self, request, *args, **kwargs):
        serializer = GoogleCalendarEventDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_calendar_id = serializer.validated_data["user_calendar_id"]
        event_id = serializer.validated_data["event_id"]

        user_calendar = get_object_or_404(UserCalendar, id=user_calendar_id, user=request.user)
        google_calendar_id = user_calendar.google_calendar_id

        calendar_service = GoogleCalendarService()
        calendar_service.delete_event(request.user, google_calendar_id, event_id)

        event_deleted = False
        deleted_count, _ = Event.objects.filter(
            user_calendar=user_calendar,
            google_event_id=event_id,
        ).delete()
        if deleted_count:
            event_deleted = True

        return Response(
            {"success": "Событие успешно удалено", "event_deleted": event_deleted},
            status=status.HTTP_204_NO_CONTENT
        )


class SyncUserCalendarEventsApi(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Синхронизировать события с Google и вернуть актуальные события из БД",
        manual_parameters=[
            openapi.Parameter('start', openapi.IN_QUERY, description="Дата начала (%Y-%m-%d)", type=openapi.TYPE_STRING),
            openapi.Parameter('end', openapi.IN_QUERY, description="Дата окончания (%Y-%m-%d)", type=openapi.TYPE_STRING),
        ],
        responses={
            200: EventSerializer(many=True),
            400: openapi.Response('Неверный формат дат или отсутствуют параметры start и end'),
            500: openapi.Response('Ошибка сервера')
        }
    )
    def post(self, request, *args, **kwargs):
        base_api = UserCalendarEventsApi()
        start_dt, end_dt, error_response = base_api._get_date_range(request)
        if error_response:
            return error_response

        calendar_service = GoogleCalendarService()
        calendar_service.sync_events_for_user(
            request.user,
            start_dt.isoformat(),
            end_dt.isoformat(),
        )

        events = base_api._get_events_from_db(request.user, start_dt, end_dt)
        return Response(events, status=status.HTTP_200_OK)


class UserCalendarListApi(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Получить список календарей пользователя",
        responses={
            200: UserCalendarSerializer(many=True),
            404: openapi.Response('Календари не найдены', examples={
                'application/json': {"error": "У пользователя нет календарей"}
            }),
            500: openapi.Response('Ошибка сервера')
        }
    )
    def get(self, request, *args, **kwargs):
        try:
            user_calendars = UserCalendar.objects.filter(user=request.user)
            if not user_calendars.exists():
                return Response({"error": "У пользователя нет календарей"}, status=status.HTTP_404_NOT_FOUND)

            serializer = UserCalendarSerializer(user_calendars, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except UserCalendar.DoesNotExist:
            return Response({"error": "Календари не найдены"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            raise e


class UpdateUserCalendarApi(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Обновить список календарей пользователя",
        responses={
            200: UserCalendarSerializer(many=True),
            500: openapi.Response('Ошибка сервера')
        }
    )
    def post(self, request, *args, **kwargs):
        try:
            # Сохраняем выбранные календари из payload до удаления
            payload = request.data if request.data else []
            selected_states = {}
            if isinstance(payload, list):
                for cal in payload:
                    gc_id = cal.get('google_calendar_id') or cal.get('calendar_id')
                    if gc_id and 'selected' in cal:
                        selected_states[str(gc_id)] = bool(cal['selected'])

            UserCalendar.objects.filter(user=request.user).delete()
            calendar_service = GoogleCalendarService()
            calendar_service.create_user_calendars(request.user)

            for gc_id, selected in selected_states.items():
                if not selected and UserCalendar.objects.filter(
                    user=request.user,
                    google_calendar_id=gc_id,
                    primary=True,
                ).exists():
                    raise ValidationError("Нельзя отключить основной календарь")

            # Применяем сохранённые состояния selected из payload
            for gc_id, selected in selected_states.items():
                UserCalendar.objects.filter(
                    user=request.user,
                    google_calendar_id=gc_id
                ).update(selected=selected)

            user_calendars = UserCalendar.objects.filter(user=request.user)
            serializer = UserCalendarSerializer(user_calendars, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            raise e
            # return Response({"error": "Внутренняя ошибка сервера"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RefreshUserCalendarsApi(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Повторно загрузить список календарей пользователя из Google и обновить БД",
        responses={
            200: UserCalendarSerializer(many=True),
            500: openapi.Response('Ошибка сервера')
        }
    )
    def post(self, request, *args, **kwargs):
        calendar_service = GoogleCalendarService()
        user_calendars = calendar_service.sync_user_calendars_safely(request.user)

        serializer = UserCalendarSerializer(user_calendars, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ToggleUserCalendarSelectApi(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(    
        operation_description="Переключить активный календарь пользователя",
        manual_parameters=[
            openapi.Parameter('google_calendar_id', openapi.IN_QUERY, description='Google calendar ID (строка)', type=openapi.TYPE_STRING)
        ],
        responses={
            200: openapi.Response('Календарь успешно переключен', examples={
                'application/json': {"success": "Календарь успешно переключен", "selected": True}
            })
        }
    )
    def post(self, request, *args, **kwargs):
        google_calendar_id = request.data.get('google_calendar_id')
        calendar_service = GoogleCalendarService()
        selected = calendar_service.toggle_calendar_select(request.user, google_calendar_id)
        return Response({"success": "Календарь успешно переключен", "selected": selected}, status=status.HTTP_200_OK)
    
    
class EventFromTaskApi(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Создать событие на основе задачи",
        manual_parameters=[
            openapi.Parameter('task_id', openapi.IN_QUERY, description="ID задачи", type=openapi.TYPE_INTEGER),
            openapi.Parameter('user_calendar_id', openapi.IN_QUERY, description="ID календаря из базы данных", type=openapi.TYPE_INTEGER),
            openapi.Parameter('start', openapi.IN_QUERY, description="Дата начала (%Y-%m-%d)", type=openapi.TYPE_STRING),
            openapi.Parameter('end', openapi.IN_QUERY, description="Дата окончания (%Y-%m-%d)", type=openapi.TYPE_STRING),
        ],
        responses={
            201: GoogleCalendarEventSerializer(many=False),
            400: openapi.Response('Неверный формат дат или отсутствуют параметры start и end', examples={
                'application/json': {"error": "Параметры start и end обязательны"}
            }),
            404: openapi.Response('Задача не найдена'),
            500: openapi.Response('Ошибка сервера')
        }
    )
    def post(self, request, *args, **kwargs):
        serializer = EventFromTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        task = get_object_or_404(Task, id=validated['task_id'], user=request.user)
        user_calendar = get_object_or_404(UserCalendar, id=validated['user_calendar_id'], user=request.user)

        try:
            with transaction.atomic():
                # 1. Готовим событие
                event_data = {
                    "summary": task.title,
                    "description": task.notes,
                    "start": {"dateTime": validated["start"].isoformat()},
                    "end": {"dateTime": validated["end"].isoformat()},
                }
                extended_event = add_event_extended_properties(event_data, task.id)

                # 2. Создаем событие
                gcal_service = GoogleCalendarService()

                calendar_event = gcal_service.create_event(
                    user=request.user,
                    google_calendar_id=user_calendar.google_calendar_id,
                    event_data=extended_event
                )
                calendar_event['user_calendar_id'] = user_calendar.id

                # 3. Сохраняем локальную запись Event, связанную с задачей
                calendar_event["summary"] = calendar_event.get("summary") or task.title
                calendar_event["description"] = calendar_event.get("description") or task.notes
                local_event = gcal_service.upsert_local_event(
                    user_calendar=user_calendar,
                    event_data=calendar_event,
                    task_id=task.id,
                    start_dt=validated["start"],
                    end_dt=validated["end"],
                    enqueue_embedding=False,
                )
                local_event.embedding = task.embedding
                local_event.embedding_status = task.embedding_status
                local_event.save(update_fields=["embedding", "embedding_status"])
                
        except Exception as e:
            return Response(
                {"error": f"Не удалось создать событие: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        response_serializer = GoogleCalendarEventSerializer(calendar_event)

        return Response(response_serializer.data, status=status.HTTP_201_CREATED)