# Release and recovery

aioarxiv uses version commits, immutable tags, and least-privilege jobs as a
release state machine. Normal publishing does not listen to arbitrary tag
pushes. `Publish` starts only from an Auto Tag dispatch after exact-SHA gates
pass, or from an explicit maintainer recovery action.

## Release invariants

A production release must satisfy all of these conditions:

- The source commit is in the history of `main`.
- `project.version` is a canonical PEP 440 version without a local segment.
- The tag is exactly `v<project.version>` and points to the source commit.
- `uv.lock` agrees with project metadata.
- PyPI and the GitHub Release use the same verified wheel and source
  distribution.
- References matching `refs/tags/v*` cannot be deleted or moved.

## Normal release

1. Open a pull request containing only release preparation and a version bump,
   updating `pyproject.toml` and `uv.lock`.
2. After it reaches `main`, CI, Coverage, and Prek run completely for that source
   SHA.
3. Completion of any required workflow wakes Auto Tag. It queries the API and
   aggregates all three results for the same SHA instead of trusting only the run
   that triggered it.
4. Auto Tag verifies that the source remains on `main` and compares
   `project.version` with the first parent. The normal path requires a strict
   version increase.
5. Before creating a tag, it builds the wheel and source distribution and
   validates Twine metadata, archive contents, and isolated installations.
6. It creates an annotated `v<version>` tag and explicitly dispatches `Publish`.
7. Publish checks out and rebuilds from the tag instead of reusing temporary
   files from the Auto Tag runner.
8. `publish-pypi` receives only `id-token: write` and uploads through the
   `release` environment's Trusted Publisher.
9. `verify-pypi` reads filenames and SHA-256 values from PyPI JSON and requires
   the remote file set to match the current artifacts exactly.
10. Only after remote distribution verification does the workflow create a
    GitHub Release and attach the same artifacts.
11. Finally, it strictly builds versioned documentation from the verified tag and
    deploys it to `/<version>/`. If that version is not older than the current
    documentation, it also updates `latest`.

Build jobs have neither PyPI OIDC nor repository write access. The PyPI job has
no GitHub Release permission, and the GitHub Release job has no PyPI
credentials. Artifacts are the only mechanism for transferring distributions
between these permission boundaries.

## TestPyPI rehearsal

`Publish (TestPyPI)` is a maintainer-only manual workflow and is not a pull
request gate. It adds a unique `.dev` suffix based on UTC time and the workflow
run to the current project version, builds and validates distributions to the
same standard as production, and uploads through the `testpypi` environment's
Trusted Publisher.

TestPyPI supports manual inspection of installation, dependencies, and metadata.
It does not replace the production source, tag, version, and PyPI hash
invariants.

## Recovery paths

| Failure | Recovery |
| --- | --- |
| A required workflow fails | Fix it in a new pull request; do not create a tag manually |
| Auto Tag distribution preflight fails before tag creation | Fix the infrastructure and wait for all three gates on the current `main` SHA; manually run Auto Tag from the default branch with the complete `source_sha` |
| The tag exists, but Publish did not start or failed | Manually run Publish from the default branch or matching tag with the existing `release_tag` |
| PyPI upload succeeded, but the GitHub Release or documentation failed | Rerun Publish for the same tag; `skip-existing` and remote hash verification confirm the published bytes |
| TestPyPI fails | Fix the problem and run it manually again; every run receives a new unique development version |

### Recovery before tag creation

Auto Tag's manual entry point is not an arbitrary commit publisher. It requires:

- `source_sha` to be a complete lowercase 40-character commit SHA;
- the workflow definition to run from the default branch;
- the source to equal the current `main` tip;
- CI, Coverage, and Prek to have succeeded for that source SHA;
- the current version not to be lower than its first parent's version;
- the target version tag not to exist; and
- the complete distribution preflight to pass again before tag creation.

A failure before tag creation commonly leaves a later repair commit with the
same version as its first parent. Recovery mode permits equality only for this
case. It cannot publish an older historical commit or replace an existing tag.

### Recovery after tag creation

When Publish is run manually, the workflow ref must be the default branch or the
tag matching the input. Publish still rechecks tag format, `main` ancestry, tag
target, project version, lockfile, build results, and PyPI hashes. Manual
dispatch does not bypass release invariants.

!!! danger "Never move a published tag"

    Do not handle a partial failure by deleting or force-pushing a tag, or by
    republishing the same version. Tags and PyPI files are immutable release
    boundaries. Recovery can complete later state but cannot change published
    bytes.

## Documentation versions

Documentation changes on `main` update the rolling `dev` version. Production
releases create a fixed version directory from the tag. `latest` is updated only
when the target version is not older than the currently deployed version, so
recovering an older release cannot roll back the default documentation.

Pages deployment is the final stage of the software release chain. If it fails,
the verified PyPI files and GitHub Release remain valid. Rerun Publish for the
same tag to complete the documentation without releasing a new software version.
