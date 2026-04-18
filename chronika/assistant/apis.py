from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from assistant.serializers import AssistantOrchestratorResponseSerializer
from assistant.services.dialog_session_store import run_assistant_turn_with_persisted_state


class AssistantMessageApi(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description=(
            "Сообщение ассистенту: полный путь FSM. Состояние диалога хранится в Postgres "
            "(сессия на пользователя), клиент передаёт только текст сообщения."
        ),
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
                description="Ответ ассистента, интенты и текущий action_plan",
                examples={
                    "application/json": {
                        "message": "",
                        "assistant_reply": "Подтвердите, пожалуйста, или скорректируйте детали.",
                        "user_id": 1,
                        "state": "waiting_confirmation",
                        "action_plan": {
                            "actions": [],
                            "entities": [],
                        },
                        "context": {"last_interaction": {}, "disambiguation_options": []},
                        "last_referenced_id": None,
                        "execution_artifact": None,
                        "intents": [
                            {
                                "item_index": 0,
                                "step": {
                                    "action": "update",
                                    "entity_type": "event",
                                    "query": {"summary": "Встреча с командой"},
                                    "fields": {},
                                    "datetime": {"start_at": "2026-04-09T18:00:00Z"},
                                    "meta": {},
                                    "filters": {},
                                },
                                "candidates": [],
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

        orchestrator_result = run_assistant_turn_with_persisted_state(user, message)
        response_payload = AssistantOrchestratorResponseSerializer.from_result(orchestrator_result)
        return Response(response_payload, status=status.HTTP_200_OK)
