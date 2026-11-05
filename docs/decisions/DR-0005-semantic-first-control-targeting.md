# DR-0005: Semantic-first control targeting; native menu limits remain open

- **Status:** Accepted direction; some native application behavior is OPEN.
- **Area:** desktop actions, accessibility, vision.

## Problem

Clicking a named control reliably is hard: comparing screenshot bytes is not a
freshness check, a dispatched click does not prove an effect, and applications
expose accessibility objects differently (for example a menu button that only
offers a focus action).

## Decision

1. **Layered flow:** the utterance or model supplies a typed intent; live
   observation grounds the target; a platform adapter performs one bounded
   action; an independent observation checks the postcondition. A model
   proposal is never evidence that a control exists or that execution
   succeeded.
2. **Prefer native semantic interfaces** where the application exposes usable
   objects ([`desktop_accessibility.py`](../../src/kyrin/actions/platforms/desktop_accessibility.py)).
   Visual evidence is a fallback under its own confidence, capture and identity
   guards. Coordinates derived from a current verified observation are
   acceptable; hard-coded or guessed coordinates are not.
3. **Provider specifics live in adapters** (for example focus-only buttons).
4. **Keep the full name** of the spoken control; model proposals must match the
   whole target phrase, and a shorter name is rejected if a longer observed name
   exists. Unique structure, not guessing, selects a menu option.
5. **Toggle state is read separately** from name and role.

## Alternatives considered

- *Replace the OCR engine only:* rejected as insufficient.
- *Free-form desktop planner:* out of scope.
- *Installed-application patches or guessed aliases:* rejected.

## Open

Some application-specific menu routes are unaccepted or `dispatched_unverified`
and their root causes are not established. Reliable support for every
application cannot be inferred from this decision.

## References

[Control policy](../actions/CONTROL_POLICY.md) ·
[Postconditions](../actions/ACTION_POSTCONDITIONS.md) ·
OCR architecture (`OCR_ARCHITECTURE.md`, source repository only)
