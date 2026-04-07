from dataclasses import asdict

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from assistant.services.intent_parser import IntentParserService


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

        try:
            parsed_intent_result = IntentParserService().parse(message)
            parsed_intent_payload = {
                "items": [asdict(item) for item in parsed_intent_result.items],
                # "raw_response": parsed_intent_result.raw_response,
            }
        except Exception as exc:
            # Не роняем эндпоинт, если parser/LLM недоступны на этом этапе.
            parsed_intent_payload = {
                "items": [],
                # "raw_response": None,
                "error": str(exc),
            }

        # Заглушка: бизнес-логика ассистента будет добавлена позже.
        return Response(
            {
                "message": message,
                "assistant_reply": "",
                "user_id": user.id,
                "intent_parser": parsed_intent_payload,
            },
            status=status.HTTP_200_OK,
        )
