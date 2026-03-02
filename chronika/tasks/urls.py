from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .apis import TaskViewSet, CategoryViewSet, TimeLogViewSet

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'timelogs', TimeLogViewSet, basename='timelog')
router.register(r'', TaskViewSet, basename='task')

urlpatterns = [
    path('', include(router.urls)),
]