from rest_framework.exceptions import APIException
from rest_framework import status
from rest_framework.views import exception_handler


# def custom_exception_handler(exc, context):
#     response = exception_handler(exc, context)

#     if response is not None and isinstance(exc, APIException):
#         response.data = {
#             "detail": exc.detail,
#             "code": exc.get_codes()
#         }

#     return response

# 
# GOOGLE EXCEPTIONS
# 
class GoogleAuthError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Ошибка авторизации через Google."
    default_code = "google_auth_error"

class GoogleNetworkError(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Ошибка соединения с Google."
    default_code = "google_network_error"

class InvalidGoogleResponseError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Некорректный ответ от сервиса Google."
    default_code = "invalid_google_response"

class ObtainGoogleAccessTokenError(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Не удалось получить google access token."
    default_code = "obtain_google_access_token_error"

class GoogleTokenExchangeError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Не удалось обменять код авторизации на токены."
    default_code = "google_token_exchange_error"

class GoogleRefreshTokenNotFoundError(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Google Refresh-токен не найден, требуется повторный запрос разрешений."
    default_code = "google_refresh_token_not_found"

class InvalidGoogleAccessTokenError(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Google Access токен не найден или истёк."
    default_code = "invalid_google_access_token"

class GoogleRefreshTokenError(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Google Refresh-токен истёк, требуется повторный запрос разрешений."
    default_code = "google_refresh_token_error"

# 
# JWT EXCEPTIONS
# 
class RefreshJWTError(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "JWT Refresh-токен не найден или истек, требуется повторная авторизация."
    default_code = "refresh_jwt_error"

class AccessJWTError(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Ошибка аутентификации."
    default_code = "access_jwt_error"


class InvalidStateError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Ошибка проверки state параметра. Возможна CSRF-атака."
    default_code = "invalid_state"

# 
# CALENDAR EXCEPTIONS
# 
class GoogleCalendarError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Ошибка при работе с Google Календарём."
    default_code = "google_calendar_error"

class CalendarSyncError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR  # HTTP 500 Internal Server Error, ошибка на сервере
    default_detail = 'Ошибка синхронизации календаря пользователя.'
    default_code = 'calendar_sync_error'

class CalendarCreationError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Ошибка при создании календаря пользователя.'
    default_code = 'calendar_creation_error'

class EventNotFoundError(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Событие не найдено."
    default_code = "event_not_found"

class CalendarNotFoundError(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Календарь не найден."
    default_code = "calendar_not_found"


# 
# SERVER EXCEPTIONS
#
class ServerError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Внутренняя ошибка сервера."
    default_code = "server_error"

class UserNotFoundError(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Пользователь не найден."
    default_code = "user_not_found"