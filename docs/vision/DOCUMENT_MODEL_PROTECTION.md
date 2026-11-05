# Document-model execution protection

(English migration of a previously Persian-only note; the original is preserved
in the private migration pre-images and in Git history. Identifiers checked in
`src/kyrin/vision/ocr/backends/{document_trust,document_sandbox}.py`.)

This contract covers only the experimental document-model path. Output text still
does not enter the click or command-execution path. The `local_files_only`
option and offline environment variables limit library downloads; they create no
security isolation.

## Provenance and manifest

The independent `APPROVED_MODELS` registry in `document_trust.py` is the
trust-decision authority. A manifest next to the model, an environment variable
or a hash computed from the installed files is not authorization. Each reviewed
entry records an HTTPS source URL, a fixed forty-character revision id, a review
reference and the complete list of relative paths with SHA-256 hashes. Before an
entry is added, the real provenance, the executable code and the expected hashes
must be checked against an independent download of the same revision. Recording a
source string alone does not prove authenticity or harmlessness of the code; the
root of trust is review and the application's own trusted distribution. There is
no publisher signature.

Currently **no document model is approved** and the registry is intentionally
empty (`APPROVED_MODELS = {}`); installed models are not offered in the UI merely
because the required file names exist. An invalid configuration, a code reference
to another repository, an extra or missing file, a symbolic link, a special file
or a hash mismatch is rejected. At run time the very bytes that were hashed are
copied into a private temporary directory and only that copy is given to the
worker, so an ordinary change of the original after verification does not alter
the run input. The copy may need disk space and time proportional to the model. It
is created under the project's runtimes on the data drive and removed at the end
or on error.

## Applicable protection

The current profile works only on Linux with `/usr/bin/bwrap`. Before every run
the same set of restrictions is probed with a harmless system program. A missing
tool, a missing option or a refused namespace/mount stops the run; there is no
unprotected execution.

- Network, PID, IPC and mount namespaces are separate; the host network, session
  socket, home and the whole project are not mounted. Only `/usr` and system
  library paths, needed parts of the selected Python environment, the model copy
  and the worker file are readable, read-only. The permanent runtime cache,
  including possible authentication data, is not mounted.
- The environment is not inherited; home and cache are fresh in a temporary space
  capped at 256 MB. Host devices including the GPU are not provided; automatic
  mode is currently CPU and an explicit GPU request is refused. Older GPU
  observations do not authorize this profile.
- Capabilities are dropped, nested user namespaces disabled and a separate process
  session is created. The worker has limits on CPU, file size, descriptors,
  process/thread count and the earlier CPU address-space limit. The OS process
  count depends on the user id; these are not an aggregate memory quota or a
  guarantee against memory exhaustion.
- The worker wait time is four minutes (`timeout=240` s). Output is read with a
  size cap, and the worker file-size limit also bounds output writing. Completion,
  non-zero exit and timeout clean up the process group; the namespace and launcher
  death terminate remaining children of the isolated environment. An error never
  produces success text.

The Python environment and system libraries remain part of the trusted base; the
provenance of runtime packages is not signed or locked in this card. The
application's own code, the kernel, an attacker of the same local user, aggregate
resource use and kernel vulnerabilities are outside the guarantee. These limits
do not claim full trust in model code. A suspicious runtime must not be run again:
after stopping the worker, quarantine or delete the related optional environment
separately and rebuild it from a trusted source; the application's main
environment and user data must not be deleted.

## Evidence and test limits

Tests use a checkpoint and a harmless program: unknown model, self-made manifest,
incomplete provenance, a swapped artifact, invalid model, timeout, worker exit and
a late child are checked. Where supported, the system-capability test also checks
refusal of reading files outside the list, writing to the model and network
connection; if the capability is refused, only the state "protection unavailable"
is confirmed.

In the 2026-10-24 review environment `bubblewrap 0.11.1` was installed but
namespace creation was refused. Therefore a successful confined run, a real model,
the GPU and a live session were **not** tested. Re-enabling needs independent
approval of a model and a test of this exact profile on a supported host; unit
tests do not replace it.

Tool behavior was checked against the official
[bubblewrap guide](https://github.com/containers/bubblewrap) and its
[options](https://github.com/containers/bubblewrap/blob/main/bwrap.xml), process
lifecycle against the [Python 3.14 documentation](https://docs.python.org/3.14/library/subprocess.html),
and the meaning of custom code against the
[Transformers documentation](https://huggingface.co/docs/transformers/en/custom_models).
