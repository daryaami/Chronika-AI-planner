# events/api.py
from datetime import datetime
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils.dateparse import parse_datetime

from tasks.models import Task, TimeLog
from .services import GoogleCalendarService, add_event_extended_properties
from core.exceptions import GoogleAuthError, GoogleNetworkError, GoogleRefreshTokenError
from .models import UserCalendar
from .serializers import EventFromTaskDeleteSerializer, EventFromTaskSerializer, GoogleCalendarEventCreateSerializer, GoogleCalendarEventDeleteSerializer, GoogleCalendarEventSerializer, GoogleCalendarEventUpdateSerializer, UserCalendarSerializer
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

class UserCalendarEventsApi(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Получить события для активных календарей пользователя",
        manual_parameters=[
            openapi.Parameter('start', openapi.IN_QUERY, description="Дата начала (%Y-%m-%d)", type=openapi.TYPE_STRING),
            openapi.Parameter('end', openapi.IN_QUERY, description="Дата окончания (%Y-%m-%d)", type=openapi.TYPE_STRING),
        ],
        responses={
            200: GoogleCalendarEventSerializer(many=True),
            400: openapi.Response('Неверный формат дат или отсутствуют параметры start и end', examples={
                'application/json': {"error": "Параметры start и end обязательны"}
            }),
            500: openapi.Response('Ошибка сервера')
        }
    )
    def get(self, request, *args, **kwargs):
        '''Получить события для активных календарей пользователя'''
        start = request.query_params.get('start')
        end = request.query_params.get('end')
        if not start or not end:
            return Response({"error": "Параметры start и end обязательны"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Преобразуем входящие даты в формат RFC3339 (ISO8601)
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            time_min = start_dt.isoformat() + "Z"
            time_max = end_dt.isoformat() + "Z"
        except ValueError:
            return Response({"error": "Неверный формат дат. Ожидается YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)
        
        calendar_service = GoogleCalendarService()
        try:
            events = calendar_service.get_all_events(request.user, time_min, time_max)
            return Response(events, status=status.HTTP_200_OK)

        except Exception as e:
            raise e
        
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

        # Проверяем, является ли событие задачей chronika
        extProps = event.get("extendedProperties", {}).get("private", {})
        print(extProps)
        if bool(extProps.get('chronika__touched', False)):
            if int(extProps.get('chronika__object-type', 0)) == 1:
                task_id = extProps.get('chronika__task-id', 0)
                google_event_id = event.get('id')

                try:
                    timelog = TimeLog.objects.get(task__id=task_id, google_event_id=google_event_id)
                except TimeLog.DoesNotExist:
                    # Если timelog не найден — можно логировать и пропускать
                    timelog = None

                if timelog:
                    # Получаем новые даты из события
                    start_str = event['start'].get('dateTime') or event['start'].get('date')
                    end_str = event['end'].get('dateTime') or event['end'].get('date')

                    new_start = parse_datetime(start_str) if start_str else None
                    new_end = parse_datetime(end_str) if end_str else None

                    # Сравниваем и обновляем, если есть изменения
                    changed = False
                    if new_start and timelog.start_time != new_start:
                        timelog.start_time = new_start
                        changed = True
                    if new_end and timelog.end_time != new_end:
                        timelog.end_time = new_end
                        changed = True

                    if changed:
                        timelog.save(update_fields=['start_time', 'end_time'])

        response_serializer = GoogleCalendarEventSerializer(event)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
    
    @swagger_auto_schema(
        operation_description="Удалить событие из календаря пользователя",
        request_body=GoogleCalendarEventDeleteSerializer,
        responses={
            204: openapi.Response('Событие успешно удалено', examples={
                'application/json': {"success": "Событие успешно удалено", "timelog_deleted": True}
            }),
            400: openapi.Response('Ошибка в параметрах'),
        }
    )
    def delete(self, request, *args, **kwargs):
        # user_calendar_id = request.data.get('user_calendar_id')
        # event_id = request.data.get('event_id')

        serializer = GoogleCalendarEventDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_calendar_id = serializer.validated_data["user_calendar_id"]
        event_id = serializer.validated_data["event_id"]

        # Получаем объект UserCalendar по ID из базы данных
        user_calendar = get_object_or_404(UserCalendar, id=user_calendar_id, user=request.user)
        google_calendar_id = user_calendar.google_calendar_id

        calendar_service = GoogleCalendarService()
        calendar_service.delete_event(request.user, google_calendar_id, event_id)

        # Если событие было создано из задачи — удаляем timelog
        timelog_deleted = False
        deleted_count, _ = TimeLog.objects.filter(
            task__user=request.user,
            google_event_id=event_id
        ).delete()
        if deleted_count:
            timelog_deleted = True
        
        return Response(
            {"success": "Событие успешно удалено", "timelog_deleted": timelog_deleted},
            status=status.HTTP_204_NO_CONTENT
        )


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
            return Response({"error": "Внутренняя ошибка сервера"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
        operation_description="Создать событие и timelog на основе задачи",
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
                extended_event = add_event_extended_properties(event_data, task.id) #, timelog.id)

                # 2. Создаем событие
                gcal_service = GoogleCalendarService()

                calendar_event = gcal_service.create_event(
                    user=request.user,
                    google_calendar_id=user_calendar.google_calendar_id,
                    event_data=extended_event
                )
                calendar_event['user_calendar_id'] = user_calendar.id

                # 3. Создаём timelog
                timelog = TimeLog.objects.create(
                    task=task,
                    start_time=validated["start"],
                    end_time=validated["end"],
                    google_event_id=calendar_event["id"]
                )
                
        except Exception as e:
            return Response(
                {"error": f"Не удалось создать событие: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        response_serializer = GoogleCalendarEventSerializer(calendar_event)

        print(response_serializer.data)
        print(timelog)
    
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        operation_description="Удалить событие и timelog на основе задачи",
        request_body=EventFromTaskDeleteSerializer,
        responses={
            204: openapi.Response('Событие и timelog успешно удалены', examples={
                'application/json': {"success": "Событие и timelog успешно удалены", "timelog_deleted": True}
            }),
            400: openapi.Response('Ошибка в параметрах'),
            404: openapi.Response('Задача не найдена'),
            500: openapi.Response('Ошибка сервера')
        }
    )
    def delete(self, request, *args, **kwargs):
        serializer = EventFromTaskDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        task = get_object_or_404(Task, id=validated['task_id'], user=request.user)
        user_calendar = get_object_or_404(UserCalendar, id=validated['user_calendar_id'], user=request.user)

        try:
            gcal_service = GoogleCalendarService()
            gcal_service.delete_event(
                user=request.user,
                google_calendar_id=user_calendar.google_calendar_id,
                event_id=validated["event_id"]
            )
        except Exception as e:
            return Response(
                {"error": f"Не удалось удалить событие: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        deleted_count, _ = TimeLog.objects.filter(
            task=task,
            google_event_id=validated["event_id"]
        ).delete()

        return Response(
            {
                "success": "Событие и timelog успешно удалены",
                "timelog_deleted": bool(deleted_count)
            },
            status=status.HTTP_204_NO_CONTENT
        )
    
    # @swagger_auto_schema(
    #     operation_description="Обновить событие и timelog",
    #     manual_parameters=[
    #         openapi.Parameter('start', openapi.IN_QUERY, description="Дата начала (%Y-%m-%d)", type=openapi.TYPE_STRING),
    #         openapi.Parameter('end', openapi.IN_QUERY, description="Дата окончания (%Y-%m-%d)", type=openapi.TYPE_STRING),
    #     ],
    #     responses={
    #         200: GoogleCalendarEventSerializer(many=False),
    #         400: openapi.Response('Неверный формат дат или отсутствуют параметры start и end', examples={
    #             'application/json': {"error": "Параметры start и end обязательны"}
    #         }),
    #         404: openapi.Response('Задача не найдена'),
    #         500: openapi.Response('Ошибка сервера')
    #     }
    # )
    # def put(self, request, *args, **kwargs):
    #     serializer = GoogleCalendarEventUpdateSerializer(data=request.data)
    #     serializer.is_valid(raise_exception=True)
    #     validated = serializer.validated_data

    #     gcal_service = GoogleCalendarService()

    #     try:
    #         user_calendar = get_object_or_404(UserCalendar, id=validated["user_calendar_id"], user=request.user)
    #     except Exception as e:
    #         return Response({"error": f"Календарь не найден: {str(e)}"},
    #                         status=status.HTTP_404_NOT_FOUND)

    #     google_calendar_id = user_calendar.google_calendar_id

    #     event_data = {
    #         "start": {"dateTime": validated["start"].isoformat()},
    #         "end": {"dateTime": validated["end"].isoformat()},
    #     }
    #     if validated.get("description"):
    #         event_data["description"] = validated["description"]
    #     if validated.get("summary"):
    #         event_data["summary"] = validated["summary"]

    #     extProps = validated.get("extendedProperties", {}).get("private", {})

    #     if "chronika__touched" in extProps and extProps["chronika__touched"] == True and extProps["chronika__object-type"] == 1:

    #         task = get_object_or_404(Task, id=extProps["chronika__task-id"], user=request.user)
    #         timelog = get_object_or_404(TimeLog, id=extProps["chronika__connected-timelog-id"], task=task)

    #         assert timelog.google_event_id == validated["event_id"], "event_id не совпадает с timelog.google_event_id"
            
    #         try:
    #             calendar_event = gcal_service.update_event(request.user, google_calendar_id, timelog.google_event_id, event_data)
    #         except Exception as e:
    #             return Response({"error": f"Не удалось обновить событие в Google Calendar: {str(e)}"},
    #                             status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    #         try:
    #             timelog.start_time = validated["start"]
    #             timelog.end_time = validated["end"]
    #             timelog.save()
    #         except Exception as e:
    #             return Response({"error": f"Не удалось обновить timelog: {str(e)}"},
    #                             status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    #         response_serializer = GoogleCalendarEventSerializer(calendar_event)

    #         return Response(response_serializer.data, status=status.HTTP_200_OK)

    #     else:
    #         try:
    #             calendar_event = gcal_service.update_event(request.user, google_calendar_id, validated["event_id"], event_data)
    #         except Exception as e:
    #             return Response({"error": f"Не удалось обновить событие в Google Calendar: {str(e)}"},
    #                             status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    #         response_serializer = GoogleCalendarEventSerializer(calendar_event)

    #         return Response(response_serializer.data, status=status.HTTP_200_OK)
    
    # def get(self, request, *args, **kwargs):
    #     return Response({"error": "Метод GET не поддерживается"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    # def delete(self, request, *args, **kwargs):


    



