from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from assistant.serializers import AssistantOrchestratorResponseSerializer
from assistant.services.chat_orchestrator import ChatOrchestratorService


class AssistantMessageApi(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Основной эндпоинт ассистента для приема сообщения пользователя",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["message"],
            properties={
                "message": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Сообщение пользователя",
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="Временный ответ (эндпоинт-заглушка)",
                examples={
                    "application/json": {
                        "message": "",
                        "assistant_reply": "",
                        "user_id": 1,
                        "candidates": [
                            {
                                "entity_type": "event",
                                "object_id": 123,
                                "similarity": 0.812345,
                                "payload": {
                                    "summary": "Встреча с командой",
                                    "description": "Подготовить демо",
                                    "start": "2026-04-09T18:00:00Z",
                                    "end": "2026-04-09T19:00:00Z",
                                },
                            }
                        ],
                        "intents": [
                            {
                                "item_index": 0,
                                "intent": {
                                    "intent": "update",
                                    "entity_type": "event",
                                    "query": {"summary": "Встреча с командой"},
                                    "fields": {},
                                    "datetime": {"start_at": "2026-04-09T18:00:00Z"},
                                    "meta": {},
                                    "filters": {},
                                },
                                "candidates": [
                                    {
                                        "entity_type": "event",
                                        "object_id": 123,
                                        "similarity": 0.812345,
                                        "payload": {
                                            "summary": "Встреча с командой",
                                            "description": "Подготовить демо",
                                            "start": "2026-04-09T18:00:00Z",
                                            "end": "2026-04-09T19:00:00Z",
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                },
            ),
            400: openapi.Response(
                description="Поле message не передано",
                examples={"application/json": {"error": "Поле message обязательно"}},
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        user = request.user
        message = request.data.get("message")
        if message is None:
            return Response(
                {"error": "Поле message обязательно"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        orchestrator_result = ChatOrchestratorService().process_message(
            user_id=user.id,
            message=message,
        )

        response_payload = AssistantOrchestratorResponseSerializer.from_result(orchestrator_result)
        return Response(response_payload, status=status.HTTP_200_OK)
