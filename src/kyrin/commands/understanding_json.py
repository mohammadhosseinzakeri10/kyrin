"""Validate untrusted structured model output before constructing a proposal."""

from collections.abc import Mapping

from kyrin.commands.understanding import (
    MeaningStep,
    Polarity,
    ProposedMeaning,
    RequestedOperation,
    UncertaintyKind,
    UnderstandingResult,
    UnderstandingStatus,
)

_SYSTEM_OPERATIONS = frozenset(
    {
        RequestedOperation.POWER_OFF_SYSTEM,
        RequestedOperation.RESTART_SYSTEM,
        RequestedOperation.LOG_OUT_SYSTEM,
        RequestedOperation.SUSPEND_SYSTEM,
    }
)
_ROUTES = frozenset(
    {"execute", "clarify", "confirm", "no_action", "respond", "unsupported"}
)


def decode_model_response(payload: object) -> UnderstandingResult:
    """Decode one model response; invalid or contradictory output fails closed.

    This checks structure and internal consistency, not whether the model
    understood the original utterance correctly. Its result cannot execute.
    """

    if not isinstance(payload, dict) or set(payload) - {
        "route",
        "steps",
        "uncertainty",
        "reply",
    }:
        raise ValueError("model response must be an object with known fields")
    route = payload.get("route")
    if not isinstance(route, str) or route not in _ROUTES:
        raise ValueError("invalid model route")
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or len(raw_steps) > 3:
        raise ValueError("model steps must be a list of at most three")
    uncertainty = payload.get("uncertainty", "")
    if not isinstance(uncertainty, str):
        raise ValueError("model uncertainty must be text")
    reply = payload.get("reply")
    # Some models fill an array item template on a conversational route, or
    # put the reply inside that item. Normalize only an item with no action
    # data; all populated operation fields remain invalid.
    if route == "respond" and len(raw_steps) == 1:
        item = raw_steps[0]
        if (
            isinstance(item, Mapping)
            and set(item) <= {"operation", "target", "app", "reply"}
            and all(
                item.get(field, "") == "" for field in ("operation", "target", "app")
            )
        ):
            nested_reply = item.get("reply")
            if nested_reply is None or reply is None or nested_reply == reply:
                reply = nested_reply if reply is None else reply
                raw_steps = []
    if reply is not None and (not isinstance(reply, str) or not reply.strip()):
        raise ValueError("model reply must be nonempty text")
    if route != "respond" and reply is not None:
        raise ValueError("only a conversational response may include reply text")
    if route in {"execute", "confirm"} and uncertainty.strip():
        raise ValueError("an action proposal cannot claim uncertainty")

    steps: list[MeaningStep] = []
    for raw in raw_steps:
        if not isinstance(raw, Mapping) or set(raw) - {
            "operation",
            "target",
            "app",
            "polarity",
            "state",
            "target_id",
        }:
            raise ValueError("invalid model step fields")
        operation_name = raw.get("operation")
        polarity_name = raw.get("polarity", Polarity.AFFIRMATIVE.value)
        if not isinstance(operation_name, str) or not isinstance(polarity_name, str):
            raise ValueError("invalid model operation or polarity")
        try:
            operation = RequestedOperation(operation_name)
            polarity = Polarity(polarity_name)
        except ValueError as exc:
            raise ValueError("invalid model operation or polarity") from exc
        if operation is RequestedOperation.SHOW_ALL_WINDOWS:
            if raw.get("target") not in (None, "") or raw.get("app") not in (None, ""):
                raise ValueError("window overview cannot name an application")
            steps.append(MeaningStep(operation, polarity=polarity))
            continue
        for field in ("target", "app"):
            if field in raw and (
                not isinstance(raw[field], str) or not raw[field].strip()
            ):
                raise ValueError(f"invalid model {field}")
        target = raw.get("target")
        app = raw.get("app")
        state = raw.get("state")
        target_id = raw.get("target_id")
        if state is not None and (
            operation is not RequestedOperation.VISIBLE_CONTROL
            or type(state) is not bool
        ):
            raise ValueError("state is only valid for a visible control")
        if operation is RequestedOperation.VISIBLE_CONTROL and app is not None:
            raise ValueError("visible control uses the focused window, not an app name")
        if target_id is not None and (
            operation is not RequestedOperation.VISIBLE_CONTROL
            or not isinstance(target_id, str)
            or not target_id.isdecimal()
        ):
            raise ValueError("target_id is only valid for a visible option")
        if operation in _SYSTEM_OPERATIONS:
            if target is not None or app is not None:
                raise ValueError("system proposal cannot name an app")
        elif target is None:
            raise ValueError("application proposal requires a target")
        if app is not None and operation is not RequestedOperation.OPEN_CHAT:
            # Some models repeat the same app in both fields. It carries no
            # additional target and is safe to discard; a different app is
            # contradictory and must be rejected.
            if (
                not isinstance(target, str)
                or not isinstance(app, str)
                or (app.strip().casefold() != target.strip().casefold())
            ):
                raise ValueError("app context is only valid for a chat proposal")
            app = None
        steps.append(MeaningStep(operation, target, app, polarity, state, target_id))

    if route == "execute":
        if not steps or any(
            step.operation in _SYSTEM_OPERATIONS
            or step.polarity is not Polarity.AFFIRMATIVE
            for step in steps
        ):
            raise ValueError("execute requires affirmative application steps")
        return UnderstandingResult(
            UnderstandingStatus.READY, (ProposedMeaning(tuple(steps)),)
        )
    if route == "confirm":
        if (
            len(steps) != 1
            or steps[0].operation not in _SYSTEM_OPERATIONS
            or steps[0].polarity is not Polarity.AFFIRMATIVE
        ):
            raise ValueError("confirm requires one affirmative system step")
        # Source-text recognition and the separate power flow remain mandatory.
        return UnderstandingResult(
            UnderstandingStatus.READY, (ProposedMeaning(tuple(steps)),)
        )
    if route == "no_action":
        if not steps:
            return UnderstandingResult(UnderstandingStatus.NOT_COMMAND)
        if any(step.polarity is not Polarity.NEGATED for step in steps):
            raise ValueError("no_action steps must be negated")
        return UnderstandingResult(
            UnderstandingStatus.NEGATED, (ProposedMeaning(tuple(steps)),)
        )
    if route == "respond":
        if steps or uncertainty.strip() or reply is None:
            raise ValueError("respond requires only a short reply")
        return UnderstandingResult(UnderstandingStatus.RESPOND, reply=reply.strip())
    if route == "unsupported":
        if steps:
            raise ValueError("unsupported route cannot propose steps")
        return UnderstandingResult(UnderstandingStatus.UNSUPPORTED)
    if steps and any(step.polarity is not Polarity.AFFIRMATIVE for step in steps):
        raise ValueError("clarification cannot include negated steps")
    try:
        uncertainty_kind = UncertaintyKind(uncertainty.strip().casefold())
    except ValueError:
        uncertainty_kind = UncertaintyKind.OPERATION
    return UnderstandingResult(
        UnderstandingStatus.AMBIGUOUS,
        (ProposedMeaning(tuple(steps)),) if steps else (),
        frozenset({uncertainty_kind}),
    )
