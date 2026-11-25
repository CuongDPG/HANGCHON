"""Mặt tiền của cơ chế giám sát cho module nghiệp vụ.

from app import control

control.register_action("content.publish_post", "Đăng bài lên mạng xã hội", "Nội dung",
                        default="ask", customer_facing=True)

@control.handler("content.publish_post")
async def _publish(ctx: control.ActionContext) -> control.HandlerResult: ...

outcome = await control.propose("content.publish_post", "Đăng bài: Bình giữ nhiệt", payload, preview, db=db)
"""

from app.modules.control.matching import match_names
from app.modules.control.models import ApprovalStatus, AutonomyLevel
from app.modules.control.registry import (
    ACTIONS,
    INTENTS,
    STAT_PROVIDERS,
    ActionContext,
    ActionSpec,
    CommandContext,
    CommandResult,
    HandlerResult,
    ReturnContext,
    Stat,
    UndoContext,
    handler,
    intent,
    on_returned,
    register_action,
    register_setting,
    stat_provider,
    undoer,
)
from app.modules.control.service import (
    ProposeOutcome,
    approve,
    audit,
    cancel_pending,
    get_level,
    get_setting,
    propose,
    return_item,
    set_level,
    set_setting,
    undo,
)

__all__ = [
    "ACTIONS",
    "INTENTS",
    "STAT_PROVIDERS",
    "ActionContext",
    "ActionSpec",
    "ApprovalStatus",
    "AutonomyLevel",
    "CommandContext",
    "CommandResult",
    "HandlerResult",
    "ProposeOutcome",
    "ReturnContext",
    "Stat",
    "UndoContext",
    "approve",
    "audit",
    "cancel_pending",
    "get_level",
    "get_setting",
    "handler",
    "intent",
    "match_names",
    "on_returned",
    "propose",
    "register_action",
    "register_setting",
    "return_item",
    "set_level",
    "set_setting",
    "stat_provider",
    "undo",
    "undoer",
]
