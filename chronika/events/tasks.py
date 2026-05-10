import logging

from celery import shared_task
from django.contrib.auth import get_user_model

from assistant.integrations.embeddings_model import EmbeddingsModelProvider
from core.enums import EmbeddingStatus, GoogleCalendarSyncStatus
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


@shared_task
def sync_event_to_google(event_id: int) -> bool:
    """Выгрузить локальное событие в Google Calendar (insert или patch)."""
    from events.services import GoogleCalendarService, add_event_extended_properties

    event = (
        Event.objects.select_related("user_calendar__user")
        .filter(id=event_id)
        .first()
    )
    if event is None:
        logger.warning("Event %s not found for Google Calendar sync.", event_id)
        return False

    user = event.user_calendar.user
    cal_id = event.user_calendar.google_calendar_id
    gcal = GoogleCalendarService()

    body: dict = {
        "summary": event.summary or "",
        "description": event.description or "",
    }
    if event.start:
        body["start"] = {"dateTime": event.start.isoformat()}
    if event.end:
        body["end"] = {"dateTime": event.end.isoformat()}
    add_event_extended_properties(body, event.task_id)

    try:
        if event.google_event_id:
            patched = gcal.update_event(user, cal_id, event.google_event_id, body)
            org_email = (patched.get("organizer") or {}).get("email")
            Event.objects.filter(pk=event_id).update(
                htmlLink=patched.get("htmlLink") or event.htmlLink,
                organizer_email=org_email or event.organizer_email,
                google_sync_status=GoogleCalendarSyncStatus.SYNCED,
            )
        else:
            inserted = gcal.create_event(user, cal_id, body)
            org_email = (inserted.get("organizer") or {}).get("email")
            Event.objects.filter(pk=event_id).update(
                google_event_id=inserted.get("id"),
                htmlLink=inserted.get("htmlLink"),
                organizer_email=org_email or event.organizer_email,
                google_sync_status=GoogleCalendarSyncStatus.SYNCED,
            )
        return True
    except Exception:
        logger.exception("Google Calendar sync failed for event %s.", event_id)
        Event.objects.filter(pk=event_id).update(
            google_sync_status=GoogleCalendarSyncStatus.FAILED
        )
        return False


@shared_task
def delete_remote_google_calendar_event(
    user_id: int, google_calendar_id: str, google_event_id: str
) -> bool:
    """Удалить событие в Google после того, как строка уже убрана из локальной БД."""
    from events.services import GoogleCalendarService

    User = get_user_model()
    user = User.objects.filter(pk=user_id).first()
    if user is None:
        logger.warning(
            "User %s not found; skip remote Google delete for event %s.",
            user_id,
            google_event_id,
        )
        return False
    try:
        GoogleCalendarService().delete_event(user, google_calendar_id, google_event_id)
        return True
    except Exception:
        logger.exception(
            "Remote Google Calendar delete failed for user=%s event=%s.",
            user_id,
            google_event_id,
        )
        return False
