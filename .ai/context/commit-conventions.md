# Commit Message Conventions

This project uses **Semantic Release** to automate versioning and package publishing. To ensure this works correctly, all commit messages **must** follow the [Conventional Commits](https://www.conventionalcommits.org/) specification.

## Format

```
<type>(<scope>): <subject>
```

## Types

*   **feat**: A new feature (triggers a MINOR release).
*   **fix**: A bug fix (triggers a PATCH release).
*   **docs**: Documentation only changes.
*   **style**: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc).
*   **refactor**: A code change that neither fixes a bug nor adds a feature.
*   **perf**: A code change that improves performance.
*   **test**: Adding missing tests or correcting existing tests.
*   **build**: Changes that affect the build system or external dependencies.
*   **ci**: Changes to our CI configuration files and scripts.
*   **chore**: Other changes that don't modify src or test files.
*   **revert**: Reverts a previous commit.

## Examples

*   `feat(instance): add support for new instance types`
*   `fix(install): resolve issue with brew installation`
*   `docs(readme): update installation instructions`
*   `ci(workflow): update release workflow configuration`

## Important Note

If a commit introduces a **Breaking Change**, the commit message body must start with `BREAKING CHANGE:` followed by a description of the change. This triggers a MAJOR release.