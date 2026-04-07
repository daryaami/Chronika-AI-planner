from core.enums import EmbeddingStatus
from tasks.models import Task
from tasks.tasks import generate_task_embedding


def enqueue_task_embedding(task: Task) -> None:
    task.embedding_status = EmbeddingStatus.PENDING
    task.save(update_fields=["embedding_status"])
    generate_task_embedding.delay(task.id)
