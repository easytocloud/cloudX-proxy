# Contributing to cloudX-proxy

## Development Setup

1. Clone the repository
2. Install the project and development tools:
   ```bash
   uv sync --group dev
   ```

## Tests and Linting

Both run in CI on every pull request and must pass:

```bash
# Run the test suite
uv run pytest

# Lint (configuration lives in pyproject.toml under [tool.ruff])
uv run ruff check cloudx_proxy tests

# Apply the fixes ruff can make safely
uv run ruff check --fix cloudx_proxy tests
```

### Backward compatibility

`uvx cloudX-proxy` resolves to the latest release every time it runs, so an
existing user's SSH config - written by an older version and never edited
again - is handed straight to new code. `tests/test_backward_compat.py` holds
configs exactly as earlier versions wrote them and asserts that `cleanup`
changes nothing in them but the version stamp, that they still parse, and that
every ProxyCommand shape those versions emitted is still accepted by `connect`.

Treat those fixtures as frozen. If a change makes one of them fail, the change
requires existing users to edit a file or re-run setup, which needs to be a
deliberate decision rather than a side effect.

## Publishing to PyPI

The package is automatically published to PyPI via GitHub Actions when a new release is created. Setup:

1. Register project on PyPI
2. Generate API token in PyPI (Account Settings → API tokens)
3. Add token as GitHub secret named `PYPI_TOKEN`

## Versioning

The project uses semantic-release for versioning. 
Version numbers are automatically determined based on commit messages following the conventional commits specification.

The GitHub Actions workflow will:

1. Determine next version based on commits
2. Update CHANGELOG.md
3. Create GitHub release
4. Publish to PyPI
