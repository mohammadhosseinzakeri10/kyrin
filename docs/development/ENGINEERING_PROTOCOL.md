# Human-AI engineering collaboration (summary)

This summary describes the project's engineering collaboration. See
[Contributing](../../CONTRIBUTING.md) for the public development workflow.

## Principle

KYRIN is developed with a human-owned, AI-assisted model. The human owner
understands the system, sets its direction, decides, reviews and validates, and
holds technical ownership; AI does suitable implementation and engineering work.
Standard cycle: understand, analyze, learn, design, approve, implement, explain,
test, validate, document, improve.

## Decision authority

- **Human decides:** project direction, product behavior, architecture, main
  interfaces, significant dependencies, technology changes, security-sensitive
  decisions, important data-flow changes, large scope changes and final acceptance.
- **AI may decide alone:** low-risk implementation choices (names, formatting,
  test structure, routine refactoring, boilerplate, small internal details,
  documentation wording, low-risk cleanup). Anything that could meaningfully
  affect architecture, compatibility, security, cost, performance or long-term
  maintenance is referred to the human.
- **Approval is not per line of code.** Routine implementation, tests, local
  refactoring, documentation, formatting and low-risk fixes proceed directly.
  The AI stops for approval before changing core architecture, adding a major
  dependency or replacing a main library, changing public or core interfaces or
  the main data flow, removing a core component, or causing significant security,
  performance, cost or scope consequences.

## Working rules

Inspect existing structure before changing it; teach only the knowledge needed
for the current work; propose architecture before significant implementation;
avoid unnecessary scope growth, complexity and dependencies; never guess missing
information; explain important implementation decisions; leave no important
component as an unexplained black box; write and run appropriate tests and debug
systematically; protect secrets and system security; keep changes traceable and
documentation consistent with the real project state; measure effort by
understanding and engineering quality, not code volume.

Review depth scales with impact (small, medium, major architectural change);
questions are asked when information is missing or a decision belongs to the
owner, and otherwise work continues directly.

## Definition of done for a meaningful feature

Goal and scope defined; relevant existing architecture inspected; necessary
concepts understood; design chosen; important decisions approved; implementation
complete; tests created where needed and passing, or known failures documented;
real behavior validated; important limitations known; documentation updated;
changes traceable.

Related: [Decision records](../decisions/README.md), [Contributing](../../CONTRIBUTING.md),
[Quality gate](QUALITY_GATE.md).
