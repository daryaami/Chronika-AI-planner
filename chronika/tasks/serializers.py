from rest_framework import serializers
from .models import Task, Category
from events.models import Event
from events.models import UserCalendar
from django.db.models import Q


class TaskEventSerializer(serializers.ModelSerializer):
    start_time = serializers.DateTimeField(source="start", read_only=True)
    end_time = serializers.DateTimeField(source="end", read_only=True)
    created = serializers.DateTimeField(read_only=True)
    updated = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Event
        fields = [
            'id',
            'summary',
            'description',
            'start_time',
            'end_time',
            'created',
            'updated',
            'htmlLink',
            'organizer_email',
            'google_event_id',
        ]
        read_only_fields = ['created', 'updated']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'color', 'is_default']


class TaskSerializer(serializers.ModelSerializer):
    events = TaskEventSerializer(many=True, read_only=True)
    user_calendar_id = serializers.PrimaryKeyRelatedField(
        queryset=UserCalendar.objects.all(),
        source='calendar',
        required=False
    )
    title = serializers.CharField(max_length=255, required=False)

    # Поле для чтения и записи id категории
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='category',
        required=False,
        allow_null=True
    )

    class Meta:
        model = Task
        fields = [
            'id',
            'title',
            'priority',
            'category_id',
            'duration',
            'due_date',
            'user_calendar_id',
            'completed',
            'created',
            'updated',
            'events',
            'notes',
        ]
        read_only_fields = ['created', 'updated']

    def create(self, validated_data):
        user = self.context['request'].user

        if 'calendar' not in validated_data:
            try:
                validated_data['calendar'] = user.calendars.get(primary=True)
            except UserCalendar.DoesNotExist:
                raise serializers.ValidationError("У пользователя нет основного календаря.")

        validated_data['user'] = user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop('user', None)
        return super().update(instance, validated_data)