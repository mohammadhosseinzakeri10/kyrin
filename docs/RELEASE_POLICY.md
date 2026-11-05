# Public release policy

Public `main` carries reviewed KYRIN source development under the
[MIT License](../LICENSE). It includes the application, tests, desktop
integrations and public documentation. KYRIN is an alpha project with
experimental paths and [known limits](VALIDATION.md). Publication does not
establish a support, maintenance or backport schedule.

## Published milestones

The [v0.1.0 GitHub pre-release](https://github.com/mohammadhosseinzakeri10/kyrin/releases/tag/v0.1.0)
identifies the initial portfolio milestone. Use its tag and checksums to
reproduce that source or obtain its wheel and source distribution. Subsequent
changes on `main` are tracked as unreleased until the maintainer approves a
separate version, tag and artifacts. The package version in a development
checkout alone does not identify a released artifact.

## What ships

The repository includes the source and development tools, and the package
manifest controls source-distribution contents. Keep recordings, owner-linked
evaluation evidence, settings, tokens, local state and unreviewed third-party
files out of both. Optional runtimes and models follow their upstream terms.
See the [third-party notices](../THIRD_PARTY_NOTICES.md) for bundled material.

## Publication workflow

Prepare a candidate from the public base in an isolated checkout. Review the
file manifest, license and data boundaries, verification results, and newly
reachable commits. Obtain maintainer approval before transferring a new
publication candidate to GitHub. Use a pull request and satisfy the protected
branch's required checks. Every branch in this repository is public. Keep
private work and recovery archives in a separate repository or storage.
