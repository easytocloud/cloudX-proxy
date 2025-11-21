# Project Overview

**cloudX-proxy** is a cross-platform SSH proxy command for connecting VSCode to CloudX/Cloud9 EC2 instances using AWS Systems Manager Session Manager.

## Key Features

- **Seamless SSH Connections**: Connect from VSCode to EC2 instances without direct SSH access or public IP addresses.
- **Automatic Instance Management**: Automatically starts instances if they are stopped.
- **Secure Key Distribution**: Pushes SSH keys via EC2 Instance Connect.
- **Secure Tunneling**: Uses AWS Systems Manager for SSH tunneling.
- **Cross-Platform**: Supports Windows, macOS, and Linux.
- **1Password Integration**: Optional integration for secure SSH key management.

## Prerequisites

1. **Python 3.9+**: Required for cloudX-proxy and uv package manager.
2. **AWS CLI v2**: For configuring AWS profiles and credentials.
3. **AWS Session Manager Plugin**: Enables secure tunneling through AWS Systems Manager.
4. **OpenSSH Client**: Handles SSH key management and connections.
5. **uv**: Modern Python package installer and virtual environment manager.
6. **VSCode with Remote SSH Extension**: The integrated development environment.

## Usage

### Setup Command

Automates the configuration process:

```bash
uvx cloudX-proxy setup [OPTIONS]
```

**Options:**
- `--profile`: AWS profile to use (default: 'vscode').
- `--ssh-key`: SSH key name to use (default: 'vscode').
- `--ssh-config`: Path to SSH config file (default: `~/.ssh/vscode/config`).
- `--1password`: Enable 1Password SSH agent integration.
- `--aws-env`: AWS environment directory.
- `--instance`: EC2 instance ID (skips prompt).
- `--hostname`: Hostname for SSH config.
- `--yes`: Non-interactive mode.
- `--dry-run`: Preview changes.

**What Setup Does:**
1. **Configures AWS Profile**: Creates/validates profile for IAM user.
2. **Manages SSH Keys**: Creates key pair or integrates with 1Password.
3. **Configures SSH**: Creates three-tier SSH config structure.
4. **Verifies Instance**: Checks setup status.

### Connect Command

Establishes the connection (typically used as ProxyCommand):

```bash
uvx cloudX-proxy connect INSTANCE_ID [PORT] [OPTIONS]
```

**Options:**
- `--profile`: AWS profile to use.
- `--ssh-key`: SSH key name to use.
- `--ssh-config`: Path to SSH config file.
- `--region`: AWS region.
- `--aws-env`: AWS environment directory.
- `--dry-run`: Preview connection workflow.

### List Command

Displays configured hosts:

```bash
uvx cloudX-proxy list [OPTIONS]
```

**Options:**
- `--ssh-config`: Path to SSH config file.
- `--environment`: Filter by environment.
- `--detailed`: Show instance IDs.
- `--dry-run`: Preview output.

## VSCode Configuration

After setup, configure VSCode settings (`settings.json`):

```json
{
    "remote.SSH.configFile": "~/.ssh/vscode/config",
    "remote.SSH.connectTimeout": 90,
    "remote.SSH.serverInstallTimeout": 120,
    "remote.SSH.showLoginTerminal": true,
    "remote.SSH.remotePlatform": {
        "cloudX-*": "linux"
    }
}
```

## Troubleshooting

### Common Issues
- **Python/Installation**: Ensure Python 3.9+ and `uv` are installed.
- **Setup**: Verify AWS profile format (`cloudX-{env}-{user}`) and permissions.
- **Connection**: Check VSCode SSH config path, instance status, and timeouts.
- **SSH Keys**: Verify permissions (600 for private key) and 1Password agent status.
- **AWS Credentials**: Ensure valid credentials and region configuration.
- **Session Manager**: Verify plugin installation and SSM agent status on instance.

### Diagnostic Commands

```bash
# Check versions
python --version
uvx --version

# Verify AWS
aws --version
aws sts get-caller-identity --profile your-profile

# Test Session Manager
aws ssm start-session --target i-1234567890abcdef0 --profile your-profile

# List hosts
uvx cloudx-proxy list --detailed