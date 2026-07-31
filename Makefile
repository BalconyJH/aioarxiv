.DEFAULT_GOAL := prepare

# Commands
UV ?= uv
UV_RUN ?= $(UV) run
PYTEST ?= $(UV_RUN) pytest
ZENSICAL ?= $(UV_RUN) zensical
TWINE ?= $(UV) run --no-project --with twine==6.2.0 twine
VERIFY_DISTRIBUTION ?= python3 scripts/verify_distribution.py

# Paths
PYTHON_PATHS := aioarxiv tests
RUFF_CHECK_PATHS := $(PYTHON_PATHS) pyproject.toml
DIST_DIR ?= $(CURDIR)/dist

# Options
DIST_SMOKE_PYTHON ?= 3.12
PYTEST_PARALLEL ?= -n auto --dist=loadfile

##@ General

.PHONY: help
help: ## Show available make targets.
	@echo "Available make targets:"
	@awk 'BEGIN { FS = ":.*## " } \
		/^##@ / { printf "\n%s:\n", substr($$0, 5); next } \
		/^[A-Za-z0-9_.-]+:.*## / { printf "  %-22s %s\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)

##@ Environment

.PHONY: ensure-uv
ensure-uv: ## Ensure uv is available in PATH.
	@$(UV) --version >/dev/null 2>&1 || { \
		echo "Error: '$(UV)' is not available."; \
		echo "Install uv from https://docs.astral.sh/uv/ and ensure it is in PATH,"; \
		echo "or override UV, e.g. 'make UV=/path/to/uv test'."; \
		exit 1; \
	}

.PHONY: sync sync-all
sync: sync-all ## Alias for sync-all.

sync-all: ensure-uv ## Sync all dependency groups for development.
	@echo "==> Syncing all dependency groups"
	@$(UV) sync --locked --all-groups

.PHONY: install-prek
install-prek: ensure-uv ## Install prek and git hooks.
	@echo "==> Installing prek"
	@$(UV) tool install prek
	@echo "==> Installing git hooks with prek"
	@$(UV) tool run prek install

.PHONY: prepare
prepare: sync-all install-prek ## Prepare local dev environment.
	@echo "==> Environment prepared"

##@ Distribution

.PHONY: clean-dist verify-artifacts build-artifacts
clean-dist: ## Remove local distribution artifacts.
	@echo "==> Removing distribution artifacts from $(DIST_DIR)"
	rm -rf -- "$(DIST_DIR)"

verify-artifacts: ensure-uv ## Verify archive contents and isolated installs.
	@echo "==> Verifying built distributions"
	@$(VERIFY_DISTRIBUTION) "$(DIST_DIR)" \
		--expected-version "$$($(UV) version --short)" \
		--python "$(DIST_SMOKE_PYTHON)" \
		--uv "$(UV)"

build-artifacts: ensure-uv clean-dist ## Build release artifacts (wheel + sdist).
	@echo "==> Building wheel and sdist into $(DIST_DIR)"
	@$(UV) build --no-sources --wheel --sdist --out-dir "$(DIST_DIR)"
	@echo "==> Validating package metadata"
	@$(TWINE) check "$(DIST_DIR)"/*
	@$(MAKE) verify-artifacts DIST_DIR="$(DIST_DIR)"
	@ls -la "$(DIST_DIR)"

##@ Testing

.PHONY: test
test: ensure-uv ## Run tests in parallel.
	@echo "==> Running tests"
	$(PYTEST) $(PYTEST_PARALLEL) tests

##@ Code quality

.PHONY: ruff-format ruff-format-check ruff-check lint basedpyright type-completeness ty typecheck check
ruff-format: ensure-uv ## Format Python files with Ruff.
	@echo "==> Formatting Python files with Ruff"
	$(UV_RUN) ruff format $(PYTHON_PATHS)

ruff-format-check: ensure-uv ## Check Python formatting without modifying files.
	@echo "==> Checking Python formatting with Ruff"
	$(UV_RUN) ruff format --check $(PYTHON_PATHS)

ruff-check: ensure-uv ## Run Ruff lint checks.
	@echo "==> Running Ruff checks"
	$(UV_RUN) ruff check $(RUFF_CHECK_PATHS)

lint: ruff-check ## Alias for ruff-check.

basedpyright: ensure-uv ## Run basedpyright type checking.
	@echo "==> Running basedpyright"
	$(UV_RUN) basedpyright .

type-completeness: ensure-uv ## Verify the installed package's public type surface.
	@echo "==> Verifying package type completeness"
	$(UV_RUN) basedpyright --verifytypes aioarxiv --ignoreexternal

ty: ensure-uv ## Run ty type checking.
	@echo "==> Running ty"
	$(UV_RUN) ty check $(PYTHON_PATHS)

typecheck: basedpyright type-completeness ## Run source and public API type checks.

check: ruff-format-check ruff-check typecheck ty test ## Run format, lint, type checks, and tests without modifying files.

##@ Documentation

.PHONY: docs-serve docs-build docs-deploy docs-list
docs-serve: ensure-uv ## Serve docs site locally.
	@echo "==> Serving docs locally"
	$(ZENSICAL) serve

docs-build: ensure-uv ## Build docs site.
	@echo "==> Building docs site"
	$(ZENSICAL) build --strict

docs-deploy: ensure-uv ## Deploy versioned docs locally (e.g. make docs-deploy VERSION=0.2.0).
	@echo "==> Deploying docs version $(VERSION)"
	$(UV_RUN) mike deploy --update-aliases $(VERSION) latest

docs-list: ensure-uv ## List all deployed doc versions.
	$(UV_RUN) mike list
