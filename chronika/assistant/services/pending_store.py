from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

ACTIVE_STATUSES = {"awaiting_confirmation", "needs_disambiguation"}
TERMINAL_STATUSES = {"executed", "cancelled", "expired", "failed"}


@dataclass
class PendingAction:
    id: str
    status: str
    type: str
    payload: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    slot_candidates: list[dict[str, Any]] = field(default_factory=list)
    disambiguation_candidates: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "type": self.type,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "slot_candidates": self.slot_candidates,
            "disambiguation_candidates": self.disambiguation_candidates,
            "meta": self.meta,
        }


class PendingStore:
    def __init__(self, ttl_minutes: int = 30):
        self._ttl_minutes = max(1, int(ttl_minutes))
        self._items: dict[str, PendingAction] = {}
        self._lock = Lock()

    def get(self, pending_id: str | None) -> PendingAction | None:
        if not pending_id:
            return None
        with self._lock:
            self._expire_locked()
            return self._items.get(str(pending_id))

    def create(
        self,
        action_type: str,
        payload: dict[str, Any],
        *,
        status: str,
        slot_candidates: list[dict[str, Any]] | None = None,
        disambiguation_candidates: list[dict[str, Any]] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> PendingAction:
        now = datetime.now(timezone.utc)
        item = PendingAction(
            id=f"p_{uuid4().hex[:10]}",
            status=status,
            type=action_type,
            payload=dict(payload),
            created_at=now,
            expires_at=now + timedelta(minutes=self._ttl_minutes),
            slot_candidates=list(slot_candidates or []),
            disambiguation_candidates=list(disambiguation_candidates or []),
            meta=dict(meta or {}),
        )
        with self._lock:
            self._expire_locked()
            self._items[item.id] = item
        return item

    def transition(self, pending_id: str, status: str) -> PendingAction | None:
        with self._lock:
            item = self._items.get(pending_id)
            if not item:
                return None
            item.status = status
            return item

    def active_items(self) -> list[PendingAction]:
        with self._lock:
            self._expire_locked()
            return [it for it in self._items.values() if it.status in ACTIVE_STATUSES]

    def clear(self) -> None:
        with self._lock:
            self._items = {}

    def _expire_locked(self) -> None:
        now = datetime.now(timezone.utc)
        for item in self._items.values():
            if item.status in TERMINAL_STATUSES:
                continue
            if item.expires_at <= now:
                item.status = "expired"
