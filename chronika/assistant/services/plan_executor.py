from __future__ import annotations

from typing import Any

from assistant.domain.action_plan import ActionPlan


class PlanExecutorService:
    """
    Последовательное выполнение actions из плана (интеграция с tasks/events — позже).
    """

    def execute(self, *, user_id: int, plan: ActionPlan) -> dict[str, Any]:
        _ = user_id
        _ = plan
        return {"status": "noop", "detail": "PlanExecutorService.execute not implemented"}
