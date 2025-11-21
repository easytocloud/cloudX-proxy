# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Context & Documentation

**IMPORTANT**: Before starting any task, consult the detailed documentation in `.ai/context/`:
- [Project Overview](.ai/context/project-overview.md)
- [Architecture](.ai/context/architecture.md)
- [Development & Contributing](.ai/context/development.md)

See also `.ai/roadmap/` for known issues and planned improvements.

## Development Commands

### Building and Installing

```bash
# Install in development mode
pip install -e .

# Build package
python -m build

# Install from built package
pip install dist/cloudx_proxy-*.whl
```

### Running the Application

The application is designed to be run via `uvx` (from the `uv` package manager):

```bash
# Setup (interactive)
uvx cloudx-proxy setup

# Setup (non-interactive with parameters)
uvx cloudx-proxy setup --profile myprofile --ssh-key mykey --instance i-123456789 --hostname myserver --yes

# Connect (typically called by SSH ProxyCommand, not directly)
uvx cloudx-proxy connect i-123456789 22 --profile myprofile

# List configured hosts
uvx cloudx-proxy list
```

## Development Standards

When working on this codebase, prioritize:
1. **Type safety** - Add complete type hints to new code
2. **Single responsibility** - Keep classes and methods focused
3. **Error handling** - Use specific exceptions with context
4. **Testing** - Write tests for new functionality (when framework exists)
5. **Security** - Validate all inputs and sanitize subprocess calls

## Release Process

The project uses semantic-release with GitHub Actions:
- **Automatic versioning**: Based on conventional commit messages
- **Release triggers**: Pushes to `main` branch
- **Artifacts**: GitHub releases, PyPI packages, CHANGELOG.md updates

Commit message format affects version bumps:
- `feat:` → minor version
- `fix:`, `docs:`, `style:`, etc. → patch version
