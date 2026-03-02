"""
Core views для общих endpoints
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny


class HealthCheckView(APIView):
    """
    Простой healthcheck endpoint для мониторинга работоспособности приложения
    Не требует аутентификации
    """
    permission_classes = [AllowAny]

    def get(self, request):
        """
        Возвращает статус здоровья приложения
        """
        return Response({
            "status": "healthy",
            "service": "chronika-api"
        }, status=status.HTTP_200_OK)
