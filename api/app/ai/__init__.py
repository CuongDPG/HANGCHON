"""Lớp AI — module nghiệp vụ chỉ gọi model qua đây.

from app import ai

ai.task("sourcing.parse_brief", system="...", tier="smart")      # khai báo (ai_tasks.py)

@ai.fake("sourcing.parse_brief")                                  # hàm giả cho provider fake
def _fake(inp: ParseBriefIn) -> ParseBriefOut: ...

res = await ai.run("sourcing.parse_brief", ParseBriefIn(...), ParseBriefOut)
res.output, res.run_id, res.cost_vnd, res.sources
"""

from app.ai.errors import AIBudgetExceeded, AIError, AIOutputInvalid, AIRefused, AIUnavailable
from app.ai.fakegen import fake_output
from app.ai.providers.fake import FakeRefusal
from app.ai.registry import TASKS, fake, on_budget_exceeded, task
from app.ai.runner import monthly_budget_vnd, monthly_spend_vnd, run
from app.ai.types import AIImage, AIResult, TaskSpec, Tier

__all__ = [
    "TASKS",
    "AIBudgetExceeded",
    "AIError",
    "AIImage",
    "AIOutputInvalid",
    "AIRefused",
    "AIResult",
    "AIUnavailable",
    "FakeRefusal",
    "TaskSpec",
    "Tier",
    "fake",
    "fake_output",
    "monthly_budget_vnd",
    "monthly_spend_vnd",
    "on_budget_exceeded",
    "run",
    "task",
]
