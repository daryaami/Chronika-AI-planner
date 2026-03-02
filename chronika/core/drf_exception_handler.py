# core/drf_exception_handler.py
import logging
import traceback
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

logger = logging.getLogger(__name__)

def _extract_api_code(exc):
    """
    Извлекает машиночитаемый код из APIException.
    drf APIException предоставляет get_codes(); это может быть строка или dict.
    Приводим к строке.
    """
    if hasattr(exc, "get_codes"):
        try:
            codes = exc.get_codes()
            # Если это dict (например validation errors), берём ключи/строку
            if isinstance(codes, dict):
                # Для валидации делаем 'validation_error'
                return "validation_error"
            return str(codes)
        except Exception:
            return getattr(exc, "default_code", "error")
    return getattr(exc, "default_code", "error")


def custom_exception_handler(exc, context):
    # 1) Попробуем стандартный DRF handler
    response = drf_exception_handler(exc, context)
    if response is not None:
        # сформируем единый формат ответа: { detail, code, (optional) errors }
        data = response.data

        # validation errors: DRF возвращает dict, где ключи — поля
        if isinstance(data, dict) and "detail" not in data:
            # это, скорее всего, ValidationError — сохраним исходные ошибки в поле `errors`
            detail = "Validation error"
            errors = data
        else:
            detail = data.get("detail") if isinstance(data, dict) else data
            errors = None

        code = _extract_api_code(exc)

        new_payload = {"detail": detail, "code": code}
        if errors:
            new_payload["errors"] = errors

        response.data = new_payload
        return response

    # 2) Непредвиденная ошибка — логируем и возвращаем общий ответ
    request = context.get("request")
    view = context.get("view")
    logger.exception(
        "Unhandled exception in view %s. Request: %s",
        getattr(view, "__class__", view),
        getattr(request, "path", None),
        exc_info=exc,
    )

    if settings.DEBUG:
        return Response(
            {"detail": str(exc), "code": "internal_error", "traceback": traceback.format_exc()},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {"detail": "Internal server error. Please contact support.", "code": "internal_error"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
