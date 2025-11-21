# Development & Contributing

## Development Setup

1. Clone the repository.
2. Install `uv` if not already installed:
   ```bash
   pip install uv
   ```
3. Create and activate a virtual environment:
   ```bash
   uv venv
   source .venv/bin/activate
   ```
4. Install development dependencies:
   ```bash
   uv pip install -e ".[dev]"
   ```

## Building and Installing

```bash
# Install in development mode
uv pip install -e .

# Build package
python -m build

# Install from built package
uv pip install dist/cloudX_proxy-*.whl
```

## Running the Application

The application is designed to be run via `uvx` (from the `uv` package manager) or `uv run` during development:

### Using `uvx` (Production/User Mode)

```bash
# Setup (interactive)
uvx cloudX-proxy setup

# Setup (non-interactive with parameters)
uvx cloudX-proxy setup --profile myprofile --ssh-key mykey --instance i-123456789 --hostname myserver --yes

# Connect (typically called by SSH ProxyCommand, not directly)
uvx cloudX-proxy connect i-123456789 22 --profile myprofile

# List configured hosts
uvx cloudX-proxy list
```

### Using `uv run` (Development Mode)

When developing, use `uv run` to execute the command within the project's environment:

```bash
# Setup (interactive)
uv run cloudX-proxy setup

# Setup (non-interactive with parameters)
uv run cloudX-proxy setup --profile myprofile --ssh-key mykey --instance i-123456789 --hostname myserver --yes

# Connect
uv run cloudX-proxy connect i-123456789 22 --profile myprofile

# List configured hosts
uv run cloudX-proxy list
```

## Development Standards

When working on this codebase, prioritize:
1. **Type safety**: Add complete type hints to new code.
2. **Single responsibility**: Keep classes and methods focused.
3. **Error handling**: Use specific exceptions with context.
4. **Testing**: Write tests for new functionality (when framework exists).
5. **Security**: Validate all inputs and sanitize subprocess calls.

## Release Process

The project uses semantic-release with GitHub Actions:

- **Automatic versioning**: Based on conventional commit messages.
- **Release triggers**: Pushes to `main` branch.
- **Artifacts**: GitHub releases, PyPI packages, CHANGELOG.md updates.

**Commit Message Format:**
- `feat:` → minor version
- `fix:`, `docs:`, `style:`, etc. → patch version

## Publishing to PyPI

The package is automatically published to PyPI via GitHub Actions when a new release is created. Setup:

1. Register project on PyPI.
2. Generate API token in PyPI (Account Settings → API tokens).
3. Add token as GitHub secret named `PYPI_TOKEN`.

The GitHub Actions workflow will:
1. Determine next version based on commits.
2. Update CHANGELOG.md.
3. Create GitHub release.
4. Publish to PyPI.

## Key Configuration Files

- **`pyproject.toml`**: Python packaging configuration with semantic versioning via setuptools_scm.
- **`.releaserc`**: Semantic-release configuration with conventional commits and changelog generation.
- **`.github/workflows/release.yml`**: CI/CD pipeline for automated releases to PyPI.
- **`.clinerules`**: Detailed project documentation including architecture and operating modes.