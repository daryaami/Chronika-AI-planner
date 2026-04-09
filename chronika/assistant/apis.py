from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
                        "intent_parser": {
                            "items": [
                                {
                                    "intent": "other",
                                    "entity_type": None,
                                    "query": None,
                                    "fields": {},
                                    "datetime": {},
                                    "meta": {},
                                    "filters": {},
                                }
                            ],
                            # "raw_response": None,
                        },
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

        return Response(
            {
                "message": orchestrator_result.message,
                "assistant_reply": orchestrator_result.assistant_reply,
                "user_id": orchestrator_result.user_id,
                "intent_parser": orchestrator_result.intent_parser,
            },
            status=status.HTTP_200_OK,
        )
