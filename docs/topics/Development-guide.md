# Development Guide

## Installing Dependencies {id="installing-dependencies"}

aioarxiv uses dependency groups for development and testing. Here's how to install them:

<tabs>
    <tab title="PDM" id="install-pdm">
        <code-block lang="bash">
pdm add -dG test pytest-cov@~5.0 pytest-xdist@~3.6 pytest-asyncio@~0.23 pytest-mock@>=3.14.0
        </code-block>
    </tab>
    <tab title="Poetry" id="install-poetry">
        <code-block lang="bash">
poetry add --group test pytest-cov@~5.0 pytest-xdist@~3.6 pytest-asyncio@~0.23 pytest-mock@>=3.14.0
        </code-block>
    </tab>
    <tab title="Pip" id="install-pip">
        <code-block lang="bash">
pip install pytest-cov==5.0.* pytest-xdist==3.6.* pytest-asyncio==0.23.* pytest-mock>=3.14.0
        </code-block>
    </tab>
</tabs>

## Test Structure {id="test-structure"}

```
tests/
├── __init__.py               # Test package initialization
├── conftest.py              # Shared test fixtures
│   └── fixtures:
│       - mock_config        # ArxivConfig mock
│       - mock_arxiv_client  # ArxivClient mock
│       - sample_paper       # Sample paper data
│       - sample_search_result # Sample search result
├── test_client.py          # ArxivClient tests
│   └── tests:
│       - test_init()       # Initialization test
│       - test_rate_limit_warning() # Rate limit warning test
│       - test_search()     # Search functionality test
│       - test_aggregate_search_results() # Result aggregation test
│       - test_prepare_initial_search() # Initial search prep test
├── test_config.py         # Configuration tests
│   └── tests:
│       - test_config_validation() # Config validation
│       - test_env_vars()  # Environment variables test
├── test_models.py        # Data model tests
│   └── tests:
│       - test_paper_model() # Paper model test
│       - test_search_params() # Search parameters test
└── test_utils/          # Utility function tests
    ├── __init__.py
    ├── test_arxiv_parser.py  # XML parser tests
    │   └── tests:
    │       - test_parse_entry() # Entry parsing test
    │       - test_build_result() # Result building test
    └── test_session.py      # Session management tests
        └── tests:
            - test_rate_limiting() # Rate limiting test
            - test_retries()  # Retry mechanism test
```

## Running Tests {id="running-tests"}

<tabs>
    <tab title="Basic Test Run" id="basic-test">
        <code-block lang="bash">
            pytest tests/
        </code-block>
    </tab>
    <tab title="With Coverage" id="coverage-test">
        <code-block lang="bash">
            pytest --cov=aioarxiv tests/
        </code-block>
    </tab>
    <tab title="Parallel Testing" id="parallel-test">
        <code-block lang="bash">
            pytest -n auto tests/
        </code-block>
    </tab>
</tabs>

## Development Tools {id="dev-tools"}

### Static Type Checking {id="static-type-check"}

```bash
pyright
```

### Code Formatting and Linting {id="code-lint"}

```bash
# Run ruff formatter
ruff format .

# Run ruff linter
ruff check .
```

### Pre-commit Hooks {id="pre-commit"}

```bash
# Install pre-commit hooks
pre-commit install

# Run pre-commit hooks
pre-commit run --all-files
```

### Version Management {id="version-management"}

```bash
# Bump version
bump-my-version bump patch  # or minor/major
```