import logging
from django.conf import settings
import jwt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError

from core.exceptions import AccessJWTError, GoogleRefreshTokenError, RefreshJWTError, UserNotFoundError
from users.models import CustomUser
from users.services import AuthService
from .serializers import UserSerializer

logger = logging.getLogger(__name__)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Выход пользователя и отзыв refresh токена",
        responses={
            204: openapi.Response(description="Токен успешно отозван"),
            500: "Ошибка на сервере"
        }
    )
    def post(self, request):
        refresh_jwt = request.COOKIES.get('refresh_jwt')
        if refresh_jwt:
            try:
                token = RefreshToken(refresh_jwt)
                token.blacklist()
            except Exception as e:
                logger.exception("Refresh token not valid for user %s: %s", request.user, str(e))
                pass
        
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie('refresh_jwt')
        logger.info("User %s successfully logged out. Refresh token blacklisted.", request.user)
        return response

class RefreshJWTView(APIView):
    """
    Обновляет access JWT токен, используя refresh токен.
    """
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Обновление access JWT токена",
        responses={
            200: openapi.Response(
                description="Access JWT токен успешно обновлен",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "access_jwt": openapi.Schema(type=openapi.TYPE_STRING, description="Access JWT токен")
                    }
                )
            ),
            403: openapi.Response(description="Refresh JWT токен не найден или истек"),
            500: "Ошибка на сервере"
        }    
    )
    def post(self, request):
        refresh_jwt = request.COOKIES.get('refresh_jwt')
        print('REFRESH_TOKEN: ', refresh_jwt if refresh_jwt else 'no')
        logger.debug("Received cookies for refresh: %s", request.COOKIES)
        if not refresh_jwt:
            logger.warning("Refresh token not provided in request cookies.")
            raise RefreshJWTError("Refresh token not provided in request cookies.")

        try:
            refresh = RefreshToken(refresh_jwt)
            new_access_token = str(refresh.access_token)
            logger.info("New access token generated using provided refresh token.")
            return Response(
                {"access_jwt": new_access_token},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.exception("Failed to refresh JWT: %s", str(e))
            raise RefreshJWTError(detail=str(e))

class ProfileView(APIView):
    '''Получает информацию о профиле юзера, обновляет имя и удаляет аккаунт'''
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Получение информации о текущем пользователе",
        responses={200: UserSerializer()}
    )
    def get(self, request):
        logger.info("User %s requested their profile.", request.user)
        user = UserSerializer(request.user)
        return Response(user.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Обновление имени пользователя",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'name': openapi.Schema(type=openapi.TYPE_STRING, description='Новое имя пользователя')
            },
            required=['name']
        ),
        responses={
            200: openapi.Response(description="Имя успешно обновлено", schema=UserSerializer),
            400: openapi.Response(description="Неверные данные"),
            500: openapi.Response(description="Ошибка на сервере")
        }
    )
    def patch(self, request):
        """Обновляет имя пользователя"""
        name = request.data.get('name')
        if not name:
            return Response(
                {"error": "Поле 'name' обязательно для заполнения"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not isinstance(name, str) or len(name.strip()) == 0:
            return Response(
                {"error": "Имя не может быть пустым"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        request.user.name = name.strip()
        request.user.save()
        logger.info("User %s updated their name to: %s", request.user.email, name)
        
        user_serializer = UserSerializer(request.user)
        return Response(user_serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_description="Удаление аккаунта пользователя и всей связанной информации",
        responses={
            204: openapi.Response(description="Аккаунт успешно удален"),
            500: openapi.Response(description="Ошибка на сервере")
        }
    )
    def delete(self, request):
        """Удаляет аккаунт пользователя и всю связанную информацию"""
        user_email = request.user.email
        user_id = request.user.id
        
        try:
            # Удаляем refresh токен из cookies, если он есть
            refresh_jwt = request.COOKIES.get('refresh_jwt')
            if refresh_jwt:
                try:
                    token = RefreshToken(refresh_jwt)
                    token.blacklist()
                except Exception as e:
                    logger.warning("Could not blacklist refresh token for user %s: %s", user_email, str(e))
            
            # Удаляем пользователя (все связанные данные удалятся автоматически благодаря CASCADE)
            request.user.delete()
            
            logger.info("User %s (ID: %s) account and all related data deleted successfully", user_email, user_id)
            
            response = Response(status=status.HTTP_204_NO_CONTENT)
            response.delete_cookie('refresh_jwt')
            return response
            
        except Exception as e:
            logger.exception("Error deleting user account %s: %s", user_email, str(e))
            return Response(
                {"error": "Произошла ошибка при удалении аккаунта"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class TokenPingView(APIView):
    '''Проверяет работоспособность access_jwt и refresh_jwt токенов'''
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_description="Проверка работоспособности токена",
        responses={200: openapi.Response(description="Токен работоспособен"),
                401: openapi.Response(description="Access JWT токен не найден или истек"),
                403: openapi.Response(description="Refresh JWT токен не найден или истек"),
                404: openapi.Response(description="Пользователь не найден")}
    )
    def get(self, request):
        refresh_jwt = request.COOKIES.get('refresh_jwt')
        print('ping: FOUND REFRESH TOKEN' if refresh_jwt else 'ping: No REFRESH token')
        if not refresh_jwt:
            raise RefreshJWTError("Refresh token is absent in request cookies.")
        try:
            AuthService.verify_refresh_token(refresh_jwt)
        except (AuthenticationFailed, TokenError):
            raise RefreshJWTError("Refresh token is invalid or expired.")
        
        access_token = request.headers.get("Authorization")
        if not access_token or not access_token.startswith("JWT "):
            raise AccessJWTError()
        token = access_token.split(" ")[1]


        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise AccessJWTError("Access token is expired.")
        except jwt.InvalidTokenError:
            raise AccessJWTError("Access token is invalid.")
        
        user_id = payload.get("user_id")
        if not user_id:
            raise AccessJWTError()
        
        try:
            user = CustomUser.objects.get(pk=user_id, is_active=True)
        except CustomUser.DoesNotExist:
            raise UserNotFoundError()
            
        return Response({"detail": "Tokens are valid."}, status=status.HTTP_200_OK)