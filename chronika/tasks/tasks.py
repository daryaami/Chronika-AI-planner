import logging

from celery import shared_task

from assistant.integrations.embeddings_model import EmbeddingsModelProvider
from core.enums import EmbeddingStatus
from tasks.models import Task

logger = logging.getLogger(__name__)


def _persist_task_embedding(task_id: int, **fields) -> bool:
    """Update task row by id; returns False if no row matched (e.g. deleted)."""
    updated = Task.objects.filter(id=task_id).update(**fields)
    if updated == 0:
        logger.warning(
            "Task %s not found when saving embedding fields; row may have been deleted.",
            task_id,
        )
        return False
    return True


@shared_task
def generate_task_embedding(task_id: int) -> bool:
    """
    Build and store embedding for a Task by ID.
    Uses task title + notes as source text.
    """
    task = Task.objects.filter(id=task_id).first()
    if task is None:
        logger.warning("Task %s not found for embedding generation.", task_id)
        return False

    try:
        source_text = f"{task.title}\n\n{task.notes or ''}".strip()
        if not source_text:
            logger.warning("Task %s has empty text for embedding generation.", task_id)
            _persist_task_embedding(task_id, embedding_status=EmbeddingStatus.FAILED)
            return False

        vector = EmbeddingsModelProvider.encode(source_text)
        if vector is None or len(vector) == 0:
            logger.warning("Empty embedding result for task %s.", task_id)
            _persist_task_embedding(task_id, embedding_status=EmbeddingStatus.FAILED)
            return False

        # SentenceTransformer may return numpy vector; pgvector accepts plain list.
        if hasattr(vector, "tolist"):
            vector = vector.tolist()

        return _persist_task_embedding(
            task_id,
            embedding=vector,
            embedding_status=EmbeddingStatus.COMPLETED,
        )
    except Exception:
        logger.exception("Failed to generate embedding for task %s.", task_id)
        _persist_task_embedding(task_id, embedding_status=EmbeddingStatus.FAILED)
        return False
