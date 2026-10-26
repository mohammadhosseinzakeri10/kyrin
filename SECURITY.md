# Security policy

## Supported scope

This policy covers the published KYRIN v0.1.0 source snapshot. It is an
experimental personal project with no guaranteed response time or long-term
security maintenance. There has been no independent comprehensive security
audit. Later private versions are outside this repository's support scope.

## Report a vulnerability privately

Use GitHub's **Report a vulnerability** form:

https://github.com/mohammadhosseinzakeri10/kyrin/security/advisories/new

Include the affected commit/version, component, reproduction using synthetic
data, expected boundary and observed result. Do not disclose vulnerabilities
in a public issue before coordination. Never include real permission tokens,
credentials, private recordings, personal screenshots or unrelated user data.
If the form is unavailable, open a minimal issue requesting a private reporting
channel without vulnerability details.

## Trust boundaries

- **Microphone and history:** standby pauses commands but may keep capture
  active. Full microphone shutdown and application quit are separate controls.
  Optional history stores finalized text locally and is not audio recording.
  Diagnostic tools can have their own recording/output options.
- **Desktop authority:** action execution is disabled in a fresh configuration.
  App selection, capability grants and portal consent are distinct. Broad
  trust and remembered permissions increase the authority of later commands.
- **Model output:** recognition can change meaning. Local command models
  propose structured intent; permission checks, target grounding and selected
  confirmations remain independent. These checks do not guarantee that every
  misrecognition will be detected.
- **Fresh targets:** window identity, observation generation, deadlines and
  cancellation protect action boundaries. A reported dispatch is not always
  a verified application effect. OS focus and external applications can change
  concurrently; atomicity or rollback across them is not guaranteed.
- **Local workers:** engine subprocesses and loopback services reduce coupling
  and permit lifecycle control. They are not a general security sandbox.
  Imported model/runtime code must be trusted. Document OCR has additional
  sandbox/trust checks documented separately.
- **Network:** configured recognition and command inference can run locally.
  Installing dependencies, acquiring models, and external apps may use the
  network. This project does not provide a host-wide network isolation layer.

Review [control policy](docs/actions/CONTROL_POLICY.md),
[postconditions](docs/actions/ACTION_POSTCONDITIONS.md),
[shared input sessions](docs/actions/SHARED_INPUT_SESSION_FA.md) and
[document OCR protection](docs/vision/DOCUMENT_MODEL_PROTECTION.md) before
changing security-relevant behavior. Use a disposable test account and
synthetic content when validating desktop actions.
