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
_ROUTES = frozenset({"execute", "clarify", "confirm", "no_action", "unsupported"})


def decode_model_response(payload: object) -> UnderstandingResult:
    """Decode one model response; invalid or contradictory output fails closed.

    This checks structure and internal consistency, not whether the model
    understood the original utterance correctly. Its result cannot execute.
    """

    if not isinstance(payload, dict) or set(payload) - {
        "route",
        "steps",
        "uncertainty",
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
    if route in {"execute", "confirm"} and uncertainty.strip():
        raise ValueError("an action proposal cannot claim uncertainty")

    steps: list[MeaningStep] = []
    for raw in raw_steps:
        if not isinstance(raw, Mapping) or set(raw) - {
            "operation",
            "target",
            "app",
            "polarity",
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
        for field in ("target", "app"):
            if field in raw and (
                not isinstance(raw[field], str) or not raw[field].strip()
            ):
                raise ValueError(f"invalid model {field}")
        target = raw.get("target")
        app = raw.get("app")
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
        steps.append(MeaningStep(operation, target, app, polarity))

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
