# Contributing to cloudX-proxy

## Development Setup

1. Clone the repository
2. Install development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## Publishing to PyPI

The package is automatically published to PyPI via GitHub Actions when a new release is created. Setup:

1. Register project on PyPI
2. Generate API token in PyPI (Account Settings → API tokens)
3. Add token as GitHub secret named `PYPI_TOKEN`

## Versioning

The project uses semantic-release for versioning, starting at version 2025.1.0. Version numbers are automatically determined based on commit messages following the conventional commits specification.

The GitHub Actions workflow will:
1. Determine next version based on commits
2. Update CHANGELOG.md
3. Create GitHub release
4. Publish to PyPI
