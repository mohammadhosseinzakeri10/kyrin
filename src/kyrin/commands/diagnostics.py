"""Content-free decision checkpoints; never evidence or execution authority."""

from kyrin.timing import mark

_INTERPRETATIONS = (
    "ReadyCommand", "ReadyPlan", "NeedsClarification", "DeclinedClarification",
    "IncompleteCommand", "UnrecognizedCommand", "NotACommand", "WakeOnly",
    "ConversationalReply",
)
_STATES = {
    "build": ("numbered_close_trace_v1",),
    "pending": (
        "NoneType", "PendingClarification", "PendingAppClarification",
        "PendingIntentClarification", "PendingOperationClarification",
        "PendingActionConfirmation", "PendingNumberedCloseConfirmation",
        "PendingWindowSelection",
    ),
    "rules": _INTERPRETATIONS,
    "hypothesis": _INTERPRETATIONS,
    "alternatives": tuple(str(count) for count in range(9)),
    "guard": (
        "started", "completed", "agreeing_question", "hypothesis_conflict",
        "operation_stopped",
    ),
    "result": _INTERPRETATIONS,
    "authorization": ("allowed", "denied"),
}
DECISION_STAGES = {
    f"command_diagnostic_{component}_{state}": f"command_{component}"
    for component, states in _STATES.items()
    for state in states
}


def trace(component: str, state: str) -> None:
    """Reject arbitrary labels, including accidental speech or model content."""
    stage = f"command_diagnostic_{component}_{state}"
    if stage in DECISION_STAGES:
        mark(stage)
