# Repository governance

Workflow and ruleset JSON files describe the intended contract but cannot
modify remote GitHub, PyPI, or TestPyPI settings automatically. Administrators
must configure and periodically audit the protections described here.

## Branches and tags

The repository provides two importable definitions:

- `.github/rulesets/protect-main.json`
- `.github/rulesets/protect-release-tags.json`

Import them from `Settings > Rules > Rulesets > Import a ruleset`, review each
target, and then enable the ruleset.

The `Protect main` baseline:

- blocks deletion and non-fast-forward updates of the default branch;
- requires linear history;
- permits squash merges only;
- requires at least one approval and dismisses stale approvals after new pushes;
- requires every review thread to be resolved;
- requires the branch to be up to date;
- requires `Required Checks`, `Coverage Matrix`, and `Prek` to pass; and
- defines no routine bypass.

`Protect release tags` matches `refs/tags/v*` and blocks deletion and
non-fast-forward updates while allowing Auto Tag to create new tags. When
renaming an aggregate workflow job, first let GitHub observe the new check
context, then update and re-import the ruleset. This prevents the gate from
waiting indefinitely for a nonexistent check.

## Deployment environments and Trusted Publishers

Rulesets protect Git references, while deployment environments protect
irreversible package publishing privileges. Neither replaces the other.

| GitHub environment | Workflow | Remote Trusted Publisher |
| --- | --- | --- |
| `release` | `.github/workflows/publish.yml` | PyPI project `aioarxiv` |
| `testpypi` | `.github/workflows/publish-test.yml` | TestPyPI project `aioarxiv` |

Configure both Trusted Publishers with:

- owner: `BalconyJH`
- repository: `aioarxiv`
- workflow filename: `publish.yml` or `publish-test.yml`, respectively
- environment name: `release` or `testpypi`, respectively

Do not store long-lived PyPI API tokens. A workflow requests `id-token: write`
only in the job that uploads a package, with the environment and Trusted
Publisher jointly restricting its OIDC identity. The `release` environment
should accept only normal publishing from version tags and manual recovery from
the default branch. Feature branches must not obtain production publishing
access.

## GitHub Pages

In `Settings > Pages`, deploy from the root of the `gh-pages` branch. Workflows
manage this branch completely; it is not source code and must not receive manual
edits or force pushes.

Pages contains:

- `dev/`: the rolling documentation for changes on `main`;
- `<version>/` and `latest/`: production release documentation; and
- `pr-preview/pr-<number>/`: temporary pull request previews.

These paths share one origin and provide no browser security isolation. Do not
store secrets, tokens, or trusted browser state on the Pages origin. See
[Continuous integration](ci.md#docs-preview) for the detailed risk model.

## Codecov

`CODECOV_TOKEN` is an optional repository secret. Without it, the workflow
attempts a tokenless upload. Upload failure does not override the pytest and
coverage gates. Create the secret only if the project becomes private or
Codecov requires authentication, and never store the token in workflow or
repository files.

## Initial setup order

1. Merge the workflows so GitHub observes `Required Checks`, `Coverage Matrix`,
   and `Prek` at least once.
2. Configure the `release` and `testpypi` environments.
3. Create the corresponding Trusted Publishers on PyPI and TestPyPI.
4. Configure Pages to deploy from the root of `gh-pages`.
5. Import and enable `Protect main`.
6. Import and enable `Protect release tags`.
7. Use a non-version-changing pull request to verify merge gates and the
   documentation preview.
8. Run the TestPyPI workflow manually to verify OIDC, builds, and installation.
9. Finally, verify the full release chain with a normal version pull request.

Do not test deletion or movement protection with a real `v*` tag. Audit tag
immutability through the ruleset configuration and confirm it with one normal
automated release.

## Audit checklist

After changing Actions, job names, environments, or publishing permissions,
verify that:

- the `main` ruleset still binds all three existing aggregate contexts;
- the `v*` tag ruleset is active and has no routine bypass;
- each PyPI/TestPyPI Trusted Publisher exactly matches its repository, workflow,
  and environment;
- the Pages source remains the root of `gh-pages`;
- every third-party workflow action is pinned to a full SHA;
- top-level permissions remain empty or read-only, and write permission exists
  only on the smallest necessary job;
- feature and fork pull requests cannot obtain write access or publishing OIDC;
  and
- `make check`, `make build-artifacts`, `make docs-build`, and workflow static
  analysis all pass.
