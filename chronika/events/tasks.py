import logging

from celery import shared_task

from assistant.integrations.embeddings_model import EmbeddingsModelProvider
from core.enums import EmbeddingStatus
from events.models import Event

logger = logging.getLogger(__name__)


@shared_task
def generate_event_embedding(event_id: int) -> bool:
    event = Event.objects.filter(id=event_id).first()
    if event is None:
        logger.warning("Event %s not found for embedding generation.", event_id)
        return False

    try:
        source_text = f"{event.summary or ''}\n\n{event.description or ''}".strip()
        if not source_text:
            logger.warning("Event %s has empty text for embedding generation.", event_id)
            event.embedding_status = EmbeddingStatus.FAILED
            event.save(update_fields=["embedding_status"])
            return False

        vector = EmbeddingsModelProvider.encode(source_text)
        if vector is None or len(vector) == 0:
            logger.warning("Empty embedding result for event %s.", event_id)
            event.embedding_status = EmbeddingStatus.FAILED
            event.save(update_fields=["embedding_status"])
            return False

        if hasattr(vector, "tolist"):
            vector = vector.tolist()

        event.embedding = vector
        event.embedding_status = EmbeddingStatus.COMPLETED
        event.save(update_fields=["embedding", "embedding_status"])
        return True
    except Exception:
        logger.exception("Failed to generate embedding for event %s.", event_id)
        event.embedding_status = EmbeddingStatus.FAILED
        event.save(update_fields=["embedding_status"])
        return False
