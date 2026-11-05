---
name: kyrin-technical-writing
description: Writing or substantively revising KYRIN engineering documentation in English, such as technical references and contracts under docs/, decision records in docs/decisions/, PROJECT_CONTEXT.md status updates, design notes, and verification or handoff reports. Use when a document must be created, restructured or updated to match changed behavior. Not for typo-level fixes, code comments, or conversational answers to the owner.
---

# KYRIN technical writing

`AGENTS.md` sections 2 and 11 are the policy; this file is the procedure.

## Choose the right document

- Update the document that owns the behavior (index: `docs/README.md`). Link
  to other references instead of copying their contracts.
- `PROJECT_CONTEXT.md`: change it only when status, an invariant or an open
  item changes. English only, no history, no personal data or workstation
  paths.
- Decision record: only for a meaningful decision, alternative or superseded
  approach. Use the next `DR-NNNN` number and the structure of existing
  records (Status and Area lines; Problem, Decision, Alternatives considered,
  Consequences and limits, References), and add a row to
  `docs/decisions/README.md`.
- Dated reports under `docs/development/` and `REVIEW.md` are historical
  records. Do not rewrite them to describe the current state.
- Language (`docs/LANGUAGE_POLICY.md`): new technical references are English.
  Preserve Persian learning notes and historical reports; never translate or
  rewrite them in place, and add an English reference as a separate linked
  file. A living Persian contract that governs behavior (for example
  `docs/actions/SHARED_INPUT_SESSION_FA.md`) is updated when that behavior
  changes, and its English reference is kept consistent. Never translate
  command vocabulary, literal targets or test data.

## Write precisely

- Verify each behavioral claim against the code before writing it, and cite
  the file, class or function so a reader can check it. If the code and an
  existing document disagree, report the discrepancy instead of choosing.
- Use the status vocabulary of `PROJECT_CONTEXT.md` (CONFIRMED, CURRENT
  DIRECTION, TEMPORARY / EXPERIMENTAL, PROPOSAL / IDEA, OPEN, UNVERIFIED).
  Never state a claim more strongly than its evidence; say what was tested,
  how, and what was not.
- Keep meaningful uncertainty and limits. Separate deterministic test
  results from live, hardware or model observations.
- Short sections, tables for mappings, concrete identifiers, no promotional
  wording.
- Privacy: no personal data, recordings, tokens, private evidence,
  `local-data/` contents or workstation paths (`SECURITY.md`, DR-0009).

## Check and report

```bash
python3 tools/doc-migration/check_links.py --root . --strict-anchors <changed files>
```

Report the result (0 broken links expected in changed files) and list the
changed files. Summarize the change to the owner in Persian; the document
itself stays English.
