# Contributing

Bug reports, pull requests, documentation improvements, and usage feedback are
welcome. This page describes the local development and contribution workflow.
See [Continuous integration](ci.md) for GitHub Actions responsibilities and
[Repository governance](governance.md) for remote protection settings.

## Prepare the development environment

The project uses [uv](https://docs.astral.sh/uv/) to manage Python and its
dependencies. After cloning the repository, run:

```bash
git clone https://github.com/BalconyJH/aioarxiv.git
cd aioarxiv
make prepare
```

`make prepare` synchronizes every dependency group from `uv.lock` and installs
[prek](https://github.com/j178/prek) and the Git hooks. Manage dependency
declarations through uv; do not edit dependency lists in `pyproject.toml`
directly.

## Quality checks

Before committing, run the aggregate command that mirrors the main CI gate:

```bash
make check
```

It checks Ruff formatting, Ruff lint, basedpyright, public type completeness,
and ty, while running the test suite in parallel. To isolate a failure, use:

```bash
make ruff-format         # Apply Ruff formatting
make ruff-format-check   # Check formatting without writing
make lint                # Ruff lint
make typecheck           # basedpyright and public type completeness
make ty                  # ty type checking
make test                # Parallel pytest suite
```

GitHub Actions workflows must also pass schema, zizmor, and actionlint checks.
`actionlint` uses the manual hook stage, so run it explicitly after changing
`.github/`:

```bash
uv tool run prek run --all-files
uv tool run prek run actionlint --all-files --hook-stage=manual
```

## Tests

```bash
make test
```

pytest-xdist runs test files in parallel. The current layout is:

```text
tests/
|-- conftest.py         # Session-scoped shared fixtures
|-- test_models.py      # Pydantic models
|-- test_public_api.py  # Top-level public exports
|-- test_client/        # ArxivClient and downloaders
`-- test_utils/         # Parsers, sessions, and utility functions
```

Fixed test data, including recorded Atom responses, lives in `tests/data/`.
Tests must not depend on the live arXiv service; isolate network boundaries
explicitly with fixtures or mocks.

## Build distributions

The release workflow accepts only wheels and source distributions that satisfy
the same local validation contract:

```bash
make build-artifacts
```

This target cleans `dist/`, builds both formats with `uv build --no-sources`,
runs the Twine metadata check, and installs each artifact in an isolated
environment to verify imports and version metadata.

## Documentation

The documentation is built with [Zensical](https://zensical.org/):

```bash
make docs-serve   # Serve a live local preview
make docs-build   # Run the same strict build as CI
```

Pull requests that change documentation inputs receive a temporary Pages
preview. The preview contains untrusted pull request content and shares the
production GitHub Pages origin. Do not store secrets, tokens, or trusted
`localStorage` state on that origin. See
[Continuous integration](ci.md#docs-preview) for the full trust boundary.

## Submit a pull request

1. Create a topic branch from the latest `main`.
2. Keep the change focused and add tests and documentation for behavior changes.
3. Run `make check` and the relevant additional checks for documentation,
   packaging, or workflow changes.
4. Open a pull request describing the motivation, externally visible behavior,
   and validation results.
5. Wait for `Required Checks`, `Coverage Matrix`, and `Prek` to pass, then resolve
   all review threads.

The project accepts squash merges only. Version bumps belong to the release
boundary and must not be mixed into ordinary feature or bug-fix pull requests.
See [Release and recovery](release.md) for the complete release process.

Submit bug reports through the
[Issue Tracker](https://github.com/BalconyJH/aioarxiv/issues), including
reproduction steps, expected behavior, the observed error, and the minimum
environment information required to diagnose it.
