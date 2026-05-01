from __future__ import annotations

from enum import Enum


class DialogState(str, Enum):
    IDLE = "idle"
    WAITING_CONFIRMATION = "waiting_confirmation"
    DISAMBIGUATION = "disambiguation"
    WAITING_CLARIFICATION = "waiting_clarification"
