from django.db.models import Q
from rest_framework import permissions, serializers, viewsets

from tasks.services import (
    MissingPrimaryCalendarError,
    build_task_create_kwargs,
    create_task,
    refresh_task_embedding_if_text_changed,
)

from .models import Category, Task
from .serializers import CategorySerializer, TaskSerializer


class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user
    
class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Task.objects.none()
        return Task.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        try:
            kwargs = build_task_create_kwargs(
                self.request.user, serializer.validated_data
            )
        except MissingPrimaryCalendarError:
            raise serializers.ValidationError(
                "У пользователя нет основного календаря."
            ) from None
        task = create_task(**kwargs)
        serializer.instance = task

    def perform_update(self, serializer):
        instance = serializer.instance
        old_title = instance.title
        old_notes = instance.notes or ""
        serializer.save()
        task = serializer.instance
        refresh_task_embedding_if_text_changed(
            task, old_title=old_title, old_notes=old_notes
        )


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Category.objects.none()
        return Category.objects.filter(
            Q(user=self.request.user) | Q(is_default=True)
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)