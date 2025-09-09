# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

cloudX-proxy is a Python CLI tool that enables SSH connections from VSCode to EC2 instances using AWS Systems Manager Session Manager. It eliminates the need for direct SSH access or public IP addresses by creating secure tunnels through AWS SSM.

### Core Architecture

The application consists of three main modules:

- **`cli.py`**: Click-based command-line interface with three main commands:
  - `setup`: Configure AWS profiles, SSH keys, and SSH configuration
  - `connect`: Establish connection to EC2 instance via SSM (used internally by SSH)
  - `list`: Display configured SSH hosts

- **`core.py`**: `CloudXProxy` class that handles the connection workflow:
  1. Check instance status via SSM
  2. Start instance if needed and wait for online status
  3. Push SSH public key via EC2 Instance Connect
  4. Start SSM session with SSH port forwarding

- **`setup.py`**: `CloudXSetup` class that implements a comprehensive setup wizard with three-tier SSH configuration

### SSH Configuration Architecture

The setup creates a hierarchical three-tier SSH configuration:

1. **Generic (cloudx-*)**: Common settings for all environments (user, keepalive, multiplexing)
2. **Environment (cloudx-{env}-*)**: Environment-specific settings (authentication, ProxyCommand)
3. **Host (cloudx-{env}-hostname)**: Instance-specific settings (HostName = instance ID)

This approach minimizes duplication and creates clear inheritance patterns.

### Security Model

Primary security is enforced through AWS IAM/SSM rather than SSH:
- AWS Systems Manager controls access via IAM permissions
- EC2 Instance Connect temporarily injects SSH public keys per session
- No inbound SSH ports needed - all traffic flows through SSM tunneling
- CloudTrail logs all connection attempts and key pushes

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

### Release Process

The project uses semantic-release with GitHub Actions:

- **Automatic versioning**: Based on conventional commit messages
- **Release triggers**: Pushes to `main` branch
- **Artifacts**: GitHub releases, PyPI packages, CHANGELOG.md updates

Commit message format affects version bumps:
- `feat:` → minor version
- `fix:`, `docs:`, `style:`, etc. → patch version

### 1Password Integration

The `--1password` flag enables comprehensive SSH key management through 1Password's secure vault system and SSH agent. This integration provides a complete workflow for creating, managing, and using SSH keys without exposing private keys to the filesystem.

#### Prerequisites
- 1Password CLI installed and available in PATH
- User authenticated to 1Password (`op account list` succeeds)
- 1Password SSH agent enabled and running (`~/.1password/agent.sock` exists)

#### Key Discovery and Management Workflow
1. **Existing Key Search**: Searches all 1Password vaults for SSH keys matching the specified name
2. **Key Naming Convention**: Uses consistent naming with prefix "cloudX SSH Key - {keyname}"
3. **Vault Selection**: 
   - If vault specified via `--1password VaultName`, uses that vault
   - If specified vault not found, prompts user to select from available vaults
   - In interactive mode, displays all available vaults for selection
4. **Key Creation**: Creates new SSH key pair directly in 1Password vault if no existing key found
5. **Public Key Export**: Exports public key to filesystem at expected SSH config location

#### SSH Configuration Generated
When using 1Password integration, the SSH configuration includes:
- `IdentityAgent ~/.1password/agent.sock` - Points to 1Password SSH agent
- `IdentityFile {keyfile}.pub` - References public key file to limit key search
- `IdentitiesOnly yes` - Prevents SSH from trying other keys in agent

#### Error Handling and Fallbacks
- If 1Password CLI unavailable: Prompts user to continue with standard SSH key setup
- If authentication fails: Provides setup instructions and troubleshooting guidance  
- If key creation fails: Falls back to standard SSH key generation
- If SSH agent unavailable: Warns user and provides configuration guidance

#### Security Benefits
- Private keys never touch the filesystem
- Centralized key management across devices
- Audit trail through 1Password logging
- Automatic key rotation capabilities
- Integration with 1Password's biometric authentication

### AWS Environment Support

The `--aws-env` parameter enables AWS profile organization:
- Looks for credentials in `~/.aws/aws-envs/{env}/` instead of `~/.aws/`
- Sets `AWS_CONFIG_FILE` and `AWS_SHARED_CREDENTIALS_FILE` environment variables
- Supports multiple isolated AWS environments

## Key Configuration Files

- **`pyproject.toml`**: Python packaging configuration with semantic versioning via setuptools_scm
- **`.releaserc`**: Semantic-release configuration with conventional commits and changelog generation
- **`.github/workflows/release.yml`**: CI/CD pipeline for automated releases to PyPI
- **`.clinerules`**: Detailed project documentation including architecture and operating modes

## Code Quality Notes

- Uses modern Python features (pathlib, type hints, f-strings)
- Supports Python 3.9+ (recently updated from 3.8+)
- No test suite currently exists
- Uses Click for CLI with proper help text and option validation
- Implements comprehensive error handling with user-friendly messages
- Cross-platform support (Windows, macOS, Linux) with platform-specific adjustments

## Code Quality and Architecture

### Current State
- No automated testing framework configured
- Monolithic CloudXSetup class (983 lines) violating SRP
- Limited type coverage (~60%) and error handling
- Security vulnerabilities in subprocess handling
- High technical debt impacting maintainability

### Improvement Documentation
For comprehensive analysis and improvement plans, see:
- **[ARCHITECTURE_REVIEW.md](./ARCHITECTURE_REVIEW.md)** - Detailed code quality analysis and security review
- **[IMPROVEMENT_ROADMAP.md](./IMPROVEMENT_ROADMAP.md)** - 6-phase improvement plan with timeline and priorities

### Development Standards
When working on this codebase, prioritize:
1. **Type safety** - Add complete type hints to new code
2. **Single responsibility** - Keep classes and methods focused
3. **Error handling** - Use specific exceptions with context
4. **Testing** - Write tests for new functionality (when framework exists)
5. **Security** - Validate all inputs and sanitize subprocess calls

## Known Issues
