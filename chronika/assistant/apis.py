from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from assistant.pipeline_log import bind_context, clear_context, event, log_exception, new_request_id, pretty_data, trace
from assistant.services.dialog_session_store import (
    clear_user_assistant_session,
    get_session_history_payload,
    run_assistant_turn_with_persisted_state,
    run_assistant_ui_action,
)


class AssistantMessageApi(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description=(
            "Текстовое сообщение ассистенту. Ответ: только message_id, state, blocks (UI-протокол)."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["message"],
            properties={
                "message": openapi.Schema(type=openapi.TYPE_STRING),
                "client_context": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message_id": openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="public_id последнего ответа ассистента (опционально)",
                        ),
                    },
                ),
            },
        ),
        responses={200: openapi.Response("Ответ с blocks")},
    )
    def post(self, request, *args, **kwargs):
        user = request.user
        bind_context(
            request_id=new_request_id(),
            user_id=getattr(user, "id", None),
            endpoint="AssistantMessageApi.post",
        )
        try:
            message = request.data.get("message")
            if message is None:
                event(
                    "api.message.validation",
                    caller="AssistantMessageApi.post",
                    error="missing message",
                )
                return Response(
                    {"error": "Поле message обязательно"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            client_context = request.data.get("client_context")
            client_message_id = None
            if isinstance(client_context, dict):
                client_message_id = client_context.get("message_id")

            text = str(message)
            trace(
                "HTTP POST /assistant/message: запрос",
                тело_кратко=pretty_data(
                    {
                        "message": text,
                        "client_context": {"message_id": client_message_id},
                    }
                ),
            )
            orchestrator_result, message_id, blocks = run_assistant_turn_with_persisted_state(
                user,
                message,
                client_message_id=client_message_id,
            )
            payload = {
                "message_id": message_id,
                "state": orchestrator_result.state,
                "blocks": blocks,
            }
            trace(
                "HTTP POST /assistant/message: ответ на фронт (полное тело)",
                response_json=pretty_data(payload),
            )
            return Response(payload, status=status.HTTP_200_OK)
        except ValueError as exc:
            log_exception("api.message", "AssistantMessageApi.post", exc)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            clear_context()


class AssistantActionApi(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description=(
            "Событие UI (подтверждение, выбор сущности, правка полей и т.д.). "
            "Ответ как у message: только message_id, state, blocks."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["message_id", "action"],
            properties={
                "message_id": openapi.Schema(type=openapi.TYPE_STRING),
                "client_context": openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "message_id": openapi.Schema(type=openapi.TYPE_STRING),
                    },
                ),
                "action": openapi.Schema(type=openapi.TYPE_OBJECT),
            },
        ),
        responses={200: openapi.Response("Ответ с blocks")},
    )
    def post(self, request, *args, **kwargs):
        user = request.user
        body = request.data if isinstance(request.data, dict) else {}
        bind_context(
            request_id=new_request_id(),
            user_id=getattr(user, "id", None),
            endpoint="AssistantActionApi.post",
        )
        try:
            trace(
                "HTTP POST /assistant/action: запрос",
                request_json=pretty_data(body),
            )
            orchestrator_result, message_id, blocks = run_assistant_ui_action(user, body)
            payload = {
                "message_id": message_id,
                "state": orchestrator_result.state,
                "blocks": blocks,
            }
            trace(
                "HTTP POST /assistant/action: ответ на фронт (полное тело)",
                response_json=pretty_data(payload),
            )
            return Response(payload, status=status.HTTP_200_OK)
        except ValueError as exc:
            log_exception("api.action", "AssistantActionApi.post", exc)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            clear_context()


class AssistantHistoryApi(APIView):
    """Полная история сообщений текущей сессии ассистента."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description=(
            "Все сообщения сессии в хронологическом порядке (user/assistant) "
            "и актуальное state сессии."
        ),
        responses={200: openapi.Response("session_id, state, messages[]")},
    )
    def get(self, request, *args, **kwargs):
        user = request.user
        bind_context(
            request_id=new_request_id(),
            user_id=getattr(user, "id", None),
            endpoint="AssistantHistoryApi.get",
        )
        try:
            payload = get_session_history_payload(user)
            trace("HTTP GET /assistant/history", response_json=pretty_data(payload))
            return Response(payload, status=status.HTTP_200_OK)
        finally:
            clear_context()


class AssistantClearChatApi(APIView):
    """Полная очистка чата: сообщения, FSM, план, контекст."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description=(
            "Удаляет все сообщения текущей сессии и сбрасывает диалог: state=idle, "
            "пустой план и контекст, last_referenced_id=null. Строка сессии сохраняется."
        ),
        responses={200: openapi.Response("cleared, messages_deleted")},
    )
    def post(self, request, *args, **kwargs):
        user = request.user
        bind_context(
            request_id=new_request_id(),
            user_id=getattr(user, "id", None),
            endpoint="AssistantClearChatApi.post",
        )
        try:
            summary = clear_user_assistant_session(user)
            trace("HTTP POST /assistant/clear", response_json=pretty_data(summary))
            return Response(summary, status=status.HTTP_200_OK)
        finally:
            clear_context()
