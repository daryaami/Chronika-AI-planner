from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DialogIntent(str, Enum):
    CONFIRM = "confirm"
    REJECT = "reject"
    CANCEL = "cancel"
    SELECT = "select"
    MODIFY = "modify"
    NEW_REQUEST = "new_request"
    UNCLEAR = "unclear"


@dataclass(frozen=True)
class NewIntentCandidate:
    raw: str


@dataclass
class ReplyInterpretation:
    dialog_intent: DialogIntent
    actions: list[dict[str, Any]] = field(default_factory=list)
    target_ids: list[int] = field(default_factory=list)
    new_intent_candidate: NewIntentCandidate | None = None
    # {"index": 0, "merge": {"fields": {...}, "query": {...}, ...}}
    step_patches: list[dict[str, Any]] = field(default_factory=list)
