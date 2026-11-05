# Public release policy

## Initial portfolio release

KYRIN v0.1.0 is the initial public, open-source portfolio release. It preserves
the implementation, tests and engineering notes at this milestone under the
[MIT License](../LICENSE). The [GitHub pre-release](https://github.com/mohammadhosseinzakeri10/kyrin/releases/tag/v0.1.0)
provides a source distribution, a Python wheel and a SHA-256 checksum file.
Installation uses a developer environment and separately configured runtimes
and models.

Later versions are planned to be developed privately and are not promised for
publication in this repository. The public repository may receive corrections
to this snapshot, but has no guaranteed update, support or security-backport
schedule. GitHub issues and pull requests concern the published snapshot.

## License continuity

The MIT license on already published copies remains applicable to those
copies. The decision to keep later work private does not withdraw the rights
provided for v0.1.0. Recipients may use, modify and redistribute this release,
including commercially, while preserving its license and copyright notices.

External dependencies and model packages retain their own licenses. An MIT
license on KYRIN does not relicense Qt, downloaded weights or optional
runtimes. See [third-party notices](../THIRD_PARTY_NOTICES.md).

See GitHub's [MIT license summary](https://choosealicense.com/licenses/mit/)
for the distinction between this permissive release and later distribution
choices. The repository's license text is the controlling notice for KYRIN.

## Version identity

The public milestone uses tag `v0.1.0`, matching the package version in
`pyproject.toml`. GitHub marks the release as a pre-release because the
application is experimental. Use the tag to reproduce the original source
and the release page to obtain its build artifacts. Public `main` can carry
reviewed corrections to the snapshot. A documentation correction does not
change the tag, package version or release assets.

Keep later development in a separate private repository. Prepare public
corrections from the public base in an isolated checkout, review the changed
files and the full newly reachable commit range, and obtain maintainer approval
before sending the exact reviewed branch to GitHub. Use a pull request for
protected `main`. Every branch or tag in the public repository is public.
