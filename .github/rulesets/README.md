# Repository rulesets

This directory contains auditable GitHub ruleset definitions. GitHub does not apply
them merely because they are stored under `.github/rulesets/`; import them manually
from `Settings > Rules > Rulesets > Import a ruleset`.

- `protect-main.json` protects the default `main` branch. It blocks deletion and
  non-fast-forward updates, requires linear history, permits only squash-merged
  pull requests with at least one approval, and requires the `Required Checks`
  (`.github/workflows/ci.yml`), `Coverage Matrix`
  (`.github/workflows/coverage.yml`), and `Prek`
  (`.github/workflows/prek.yml`) status checks.
- `protect-release-tags.json` blocks deletion and non-fast-forward updates for
  `refs/tags/v*`, keeping published release tags immutable.

When renaming an aggregate workflow job, update the corresponding
`required_status_checks` context in `protect-main.json`. Wait until GitHub has
observed the new check context at least once before updating an imported ruleset.
