from rest_framework import viewsets, permissions
from django.db.models import Q
from .models import Task, Category
from .serializers import TaskSerializer, CategorySerializer
from .services import enqueue_task_embedding

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
        task = serializer.save(user=self.request.user)
        enqueue_task_embedding(task)

    def perform_update(self, serializer):
        instance = serializer.instance
        old_title = instance.title
        old_notes = instance.notes or ""
        task = serializer.save()
        text_changed = task.title != old_title or (task.notes or "") != old_notes
        if text_changed:
            enqueue_task_embedding(task)


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