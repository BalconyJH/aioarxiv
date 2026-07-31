# Continuous integration

This page describes the responsibilities, merge gates, and trust boundaries of
the GitHub Actions workflows in `.github/workflows/`. See
[Release and recovery](release.md) for the release state machine and
[Repository governance](governance.md) for remote GitHub settings.

## Workflow overview

| Workflow | File | Triggers | Responsibility |
| --- | --- | --- | --- |
| CI | `ci.yml` | `main` push, pull request, manual | Formatting, lint, typing, packaging, and wheel installation |
| Coverage | `coverage.yml` | `main` push, pull request, manual | Python 3.10–3.14 tests and coverage threshold |
| Prek | `prek.yml` | `main` push, pull request, manual | Repository hooks and GitHub Actions static analysis |
| CodeQL | `codeql.yml` | `main` push, pull request, weekly | Python security analysis |
| Docs | `docs.yml` | Documentation changes on `main`, manual | Strict build and `dev` documentation update |
| Docs PR Preview Build | `docs-pr-preview.yml` | Pull request | Build a preview artifact in a read-only context |
| Docs PR Preview Deploy | `docs-pr-preview-deploy.yml` | Preview build completed | Validate and deploy the static preview |
| Docs PR Preview Cleanup | `docs-pr-preview-cleanup.yml` | Pull request closed | Remove the matching preview |
| Auto Tag on Version Change | `auto-tag.yml` | Required workflow completed, manual recovery | Aggregate exact-SHA gates and create a version tag |
| Publish | `publish.yml` | Auto Tag dispatch, manual recovery | Publish to PyPI, create a GitHub Release, and deploy versioned docs |
| Publish (TestPyPI) | `publish-test.yml` | Manual only | Publish a unique development version for manual acceptance |

Every third-party action is pinned to a full commit SHA. Top-level permissions
are empty or read-only, and write permissions are granted only to jobs that must
create remote state. Dependabot updates GitHub Actions and uv dependencies
weekly.

## Merge gates

The importable `Protect main` ruleset binds three stable aggregate checks:

- `Required Checks` summarizes every job in CI.
- `Coverage Matrix` requires the complete Python version matrix to pass.
- `Prek` requires the repository hooks and actionlint to pass.

Aggregate jobs use `if: always()`, so a failed, cancelled, or skipped internal
job cannot be mistaken for success. The ruleset does not need to bind matrix job
names that change when Python versions or internal tasks are added.

### CI layers

| Job | Validation |
| --- | --- |
| `Ruff` | `ruff format --check` and `ruff check` |
| `Ty` | `ty check` |
| `Basedpyright` | Source type checking and `aioarxiv` public type completeness |
| `Package Build` | Wheel, source distribution, and package metadata |
| `Wheel Smoke` | Isolated installation and import on Python 3.10, 3.11, 3.13, and 3.14 |
| `Required Checks` | Aggregate all results above |

`Basedpyright` starts only after `Ruff` succeeds, avoiding runner use when
formatting or lint has already failed. `Ty` and the distribution build remain
parallel with Ruff to preserve independent feedback and minimize the successful
path's total duration.

The package build validates complete isolated wheel and source distribution
installs on Python 3.12. Wheel smoke tests cover runtime dependencies and import
boundaries on the other supported versions. The corresponding local aggregate
commands are:

```bash
make check
make build-artifacts
```

## Coverage

Coverage runs the test suite separately on Python 3.10–3.14. Every matrix entry
must reach 75% project coverage. Test logs and XML reports are retained as
artifacts for 14 days regardless of success or failure.

Codecov upload is not a correctness gate. The repository can provide
`CODECOV_TOKEN` or attempt a tokenless upload; an external service failure
cannot override the pytest and coverage results.

## Documentation builds and pull request previews { #docs-preview }

Documentation pull requests use a two-stage trust model that separates building
from deployment:

1. `Docs PR Preview Build` executes untrusted code with a read-only pull request
   token and uploads only the resulting `site/` artifact.
2. `Docs PR Preview Deploy` runs from the default branch's `workflow_run`
   definition. It resolves the current pull request again, requires the upstream
   run, pull request, and head SHA to agree, and rejects stale or ambiguous
   associations.
3. Before deployment, it accepts only regular files and directories, rejects
   symbolic links and other file types, and limits the artifact to 10,000 files
   and 100 MiB.
4. The trusted job writes only validated static content to
   `gh-pages/pr-preview/pr-<number>/`. It neither checks out the pull request
   branch nor executes programs from the artifact.
5. After the pull request closes, the cleanup workflow removes the numbered
   preview path and updates the comment.

!!! warning "The Pages origin is not a security boundary"

    Pull request previews and production documentation share the
    `https://balconyjh.github.io` origin. Public forks can control preview HTML
    and JavaScript, so that origin must not store secrets, tokens, or browser
    state trusted by production pages. Review previews with a browser profile
    that contains no sensitive authenticated state.

`Docs` applies path filtering to documentation inputs, running a strict build
and deploying the rolling `dev` version only when needed. Because it does not
produce a run for every `main` SHA, Auto Tag's exact-SHA gate aggregates only
the always-running CI, Coverage, and Prek workflows. The publish workflow builds
versioned documentation strictly again from the verified tag.

## Concurrency and exact SHAs

Pull request updates cancel stale CI, Coverage, Prek, and preview builds for the
same pull request. A `main` push instead uses its commit SHA as the concurrency
key and is not cancelled by later commits, because Auto Tag must aggregate the
complete result for one source SHA.

Auto Tag serializes multiple `workflow_run` events by source SHA. Each event
queries the GitHub API for all three required workflows on that SHA and proceeds
to version detection only when every result is `completed/success`. Publishing
thereafter depends on the resolved commit and tag, not the "latest run" or a
moving `main`.

## Diagnostics

Manual CI, Coverage, and Docs runs can enable `debug_enabled` to emit runner or
dependency snapshots. Failure logs, coverage reports, build logs, and
distributions are retained as short-lived artifacts.

Validate workflows locally with:

```bash
uv tool run prek run check-github-workflows --all-files
uv tool run prek run zizmor --all-files
uv tool run prek run actionlint --all-files --hook-stage=manual
```
