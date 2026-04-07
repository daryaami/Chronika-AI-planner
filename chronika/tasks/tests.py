from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch
from rest_framework import status
from rest_framework.test import APITestCase

from core.enums import EmbeddingStatus
from events.models import UserCalendar
from tasks.models import Category, Task
from users.models import CustomUser
from tasks.tasks import generate_task_embedding


class TasksApiTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="tasks@example.com",
            name="Tasks User",
            password="password123",
            google_id="google-tasks-1",
        )
        self.other_user = CustomUser.objects.create_user(
            email="other@example.com",
            name="Other User",
            password="password123",
            google_id="google-other-1",
        )

        self.primary_calendar = UserCalendar.objects.create(
            user=self.user,
            google_calendar_id="primary-cal-id",
            summary="Primary",
            selected=True,
            owner=True,
            primary=True,
        )
        other_calendar = UserCalendar.objects.create(
            user=self.other_user,
            google_calendar_id="other-cal-id",
            summary="Other",
            selected=True,
            owner=True,
            primary=True,
        )

        Task.objects.create(
            user=self.user,
            title="My task",
            calendar=self.primary_calendar,
        )
        Task.objects.create(
            user=self.other_user,
            title="Other task",
            calendar=other_calendar,
        )

        self.client.force_authenticate(self.user)

    def test_tasks_list_returns_only_current_user_tasks(self):
        url = reverse("task-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "My task")

    @patch("tasks.services.generate_task_embedding.delay")
    def test_task_create_uses_primary_calendar_when_not_provided(self, mocked_delay):
        url = reverse("task-list")
        response = self.client.post(
            url,
            {"title": "Task without calendar"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_task = Task.objects.get(id=response.data["id"])
        self.assertEqual(created_task.calendar_id, self.primary_calendar.id)
        self.assertEqual(created_task.user_id, self.user.id)
        self.assertEqual(created_task.embedding_status, EmbeddingStatus.PENDING)
        mocked_delay.assert_called_once_with(created_task.id)

    def test_categories_include_defaults_and_own_only(self):
        Category.objects.create(name="Default", color="#ffffff", is_default=True)
        Category.objects.create(name="Mine", color="#000000", user=self.user, is_default=False)
        Category.objects.create(
            name="Other private",
            color="#ff0000",
            user=self.other_user,
            is_default=False,
        )

        url = reverse("category-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {item["name"] for item in response.data}
        self.assertIn("Default", names)
        self.assertIn("Mine", names)
        self.assertNotIn("Other private", names)

    def test_task_detail_for_foreign_task_returns_404(self):
        foreign_task = Task.objects.filter(user=self.other_user).first()

        url = reverse("task-detail", args=[foreign_task.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("tasks.services.generate_task_embedding.delay")
    def test_task_patch_updates_own_task(self, mocked_delay):
        own_task = Task.objects.filter(user=self.user).first()

        url = reverse("task-detail", args=[own_task.id])
        response = self.client.patch(url, {"title": "Updated task"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        own_task.refresh_from_db()
        self.assertEqual(own_task.title, "Updated task")
        self.assertEqual(own_task.embedding_status, EmbeddingStatus.PENDING)
        mocked_delay.assert_called_once_with(own_task.id)

    @patch("tasks.services.generate_task_embedding.delay")
    def test_task_patch_non_text_fields_does_not_enqueue_embedding(self, mocked_delay):
        own_task = Task.objects.filter(user=self.user).first()

        url = reverse("task-detail", args=[own_task.id])
        response = self.client.patch(url, {"completed": True}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        own_task.refresh_from_db()
        self.assertTrue(own_task.completed)
        mocked_delay.assert_not_called()

    @patch("tasks.services.generate_task_embedding.delay")
    def test_task_patch_priority_does_not_enqueue_embedding(self, mocked_delay):
        own_task = Task.objects.filter(user=self.user).first()

        url = reverse("task-detail", args=[own_task.id])
        response = self.client.patch(url, {"priority": "HIGH"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mocked_delay.assert_not_called()

    @patch("tasks.services.generate_task_embedding.delay")
    def test_task_patch_due_date_does_not_enqueue_embedding(self, mocked_delay):
        own_task = Task.objects.filter(user=self.user).first()
        due = timezone.now()

        url = reverse("task-detail", args=[own_task.id])
        response = self.client.patch(url, {"due_date": due.isoformat()}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mocked_delay.assert_not_called()

    @patch("tasks.services.generate_task_embedding.delay")
    def test_task_patch_echoing_title_and_notes_does_not_enqueue_embedding(self, mocked_delay):
        own_task = Task.objects.filter(user=self.user).first()

        url = reverse("task-detail", args=[own_task.id])
        response = self.client.patch(
            url,
            {"title": own_task.title, "notes": own_task.notes, "priority": "LOW"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mocked_delay.assert_not_called()

    def test_category_create_creates_for_current_user(self):
        url = reverse("category-list")
        response = self.client.post(
            url,
            {"name": "Work", "color": "#123456", "is_default": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Category.objects.get(id=response.data["id"])
        self.assertEqual(created.user_id, self.user.id)

    def test_task_delete_removes_own_task(self):
        own_task = Task.objects.filter(user=self.user).first()

        url = reverse("task-detail", args=[own_task.id])
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Task.objects.filter(id=own_task.id).exists())

    def test_category_detail_get_patch_delete_for_own_category(self):
        category = Category.objects.create(
            name="Personal",
            color="#222222",
            user=self.user,
            is_default=False,
        )
        detail_url = reverse("category-detail", args=[category.id])

        get_response = self.client.get(detail_url)
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_response.data["name"], "Personal")

        patch_response = self.client.patch(
            detail_url,
            {"name": "Personal Updated"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        category.refresh_from_db()
        self.assertEqual(category.name, "Personal Updated")

        delete_response = self.client.delete(detail_url)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Category.objects.filter(id=category.id).exists())

    def test_category_detail_for_foreign_private_category_returns_404(self):
        foreign_category = Category.objects.create(
            name="Foreign",
            color="#333333",
            user=self.other_user,
            is_default=False,
        )
        detail_url = reverse("category-detail", args=[foreign_category.id])

        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_task_delete_for_foreign_task_returns_404(self):
        foreign_task = Task.objects.filter(user=self.other_user).first()
        url = reverse("task-detail", args=[foreign_task.id])

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TaskEmbeddingsTaskTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="embeddings@example.com",
            name="Embeddings User",
            password="password123",
            google_id="google-embeddings-1",
        )
        self.calendar = UserCalendar.objects.create(
            user=self.user,
            google_calendar_id="embeddings-cal-id",
            summary="Embeddings",
            selected=True,
            owner=True,
            primary=True,
        )

    @patch("tasks.tasks.EmbeddingsModelProvider.encode")
    def test_generate_task_embedding_updates_task_embedding_field(self, mocked_encode):
        mocked_encode.return_value = [0.0] * 1024
        task = Task.objects.create(
            user=self.user,
            title="Read chapter",
            notes="About Celery integration",
            calendar=self.calendar,
        )

        result = generate_task_embedding(task.id)

        self.assertTrue(result)
        task.refresh_from_db()
        self.assertIsNotNone(task.embedding)
        self.assertEqual(len(task.embedding), 1024)
        mocked_encode.assert_called_once()

    def test_generate_task_embedding_returns_false_when_task_missing(self):
        result = generate_task_embedding(999999)
        self.assertFalse(result)

    @patch("tasks.tasks.EmbeddingsModelProvider.encode")
    def test_generate_task_embedding_sets_failed_status_on_empty_embedding(self, mocked_encode):
        mocked_encode.return_value = []
        task = Task.objects.create(
            user=self.user,
            title="Task with failed embedding",
            notes="",
            calendar=self.calendar,
        )

        result = generate_task_embedding(task.id)

        self.assertFalse(result)
        task.refresh_from_db()
        self.assertEqual(task.embedding_status, EmbeddingStatus.FAILED)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class TaskEmbeddingsEagerIntegrationTests(APITestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="eager@example.com",
            name="Eager User",
            password="password123",
            google_id="google-eager-1",
        )
        self.calendar = UserCalendar.objects.create(
            user=self.user,
            google_calendar_id="eager-cal-id",
            summary="Eager",
            selected=True,
            owner=True,
            primary=True,
        )
        self.client.force_authenticate(self.user)

    @patch("tasks.tasks.EmbeddingsModelProvider.encode")
    def test_create_task_runs_celery_job_and_persists_embedding(self, mocked_encode):
        mocked_encode.return_value = [0.2] * 1024

        response = self.client.post(
            reverse("task-list"),
            {"title": "Eager task", "notes": "integration smoke test"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_task = Task.objects.get(id=response.data["id"])
        self.assertIsNotNone(created_task.embedding)
        self.assertEqual(len(created_task.embedding), 1024)
        self.assertEqual(created_task.embedding_status, EmbeddingStatus.COMPLETED)
