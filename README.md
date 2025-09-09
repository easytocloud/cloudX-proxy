# cloudX-proxy

[![PyPI Version](https://img.shields.io/pypi/v/cloudx-proxy.svg)](https://pypi.org/project/cloudx-proxy/)
[![Python Support](https://img.shields.io/pypi/pyversions/cloudx-proxy.svg)](https://pypi.org/project/cloudx-proxy/)
[![License](https://img.shields.io/github/license/easytocloud/cloudX-proxy.svg)](https://github.com/easytocloud/cloudX-proxy/blob/main/LICENSE)
[![Release](https://github.com/easytocloud/cloudX-proxy/actions/workflows/release.yml/badge.svg)](https://github.com/easytocloud/cloudX-proxy/actions/workflows/release.yml)
[![Security Audit](https://img.shields.io/badge/security-pip--audit-blue?logo=python)](https://github.com/easytocloud/cloudX-proxy/actions/workflows/release.yml)
[![License Check](https://img.shields.io/badge/license-MIT%20compatible-green?logo=legal)](https://github.com/easytocloud/cloudX-proxy/actions/workflows/release.yml)
[![Dependabot](https://img.shields.io/badge/dependabot-enabled-brightgreen?logo=dependabot)](https://github.com/easytocloud/cloudX-proxy/network/updates)
[![Downloads](https://img.shields.io/pypi/dm/cloudx-proxy.svg)](https://pypi.org/project/cloudx-proxy/)

A cross-platform SSH proxy command for connecting VSCode to CloudX/Cloud9 EC2 instances using AWS Systems Manager Session Manager.

## Overview

cloudX-proxy enables seamless SSH connections from VSCode to EC2 instances using AWS Systems Manager Session Manager, eliminating the need for direct SSH access or public IP addresses. It handles:

- Automatic instance startup if stopped
- SSH key distribution via EC2 Instance Connect
- SSH tunneling through AWS Systems Manager
- Cross-platform support (Windows, macOS, Linux)

## Quick Start

**TL;DR for experienced users:**

1. **Install Prerequisites:**
   ```bash
   # Install Python 3.9+, AWS CLI v2, Session Manager plugin
   pip install uv
   ```

2. **Run Setup:**
   ```bash
   # Basic setup (will prompt for AWS profile, instance ID, etc.)
   uvx cloudx-proxy setup
   
   # Or non-interactive with all parameters
   uvx cloudx-proxy setup --profile myprofile --instance i-1234567890abcdef0 --hostname myserver --yes
   ```

3. **Configure VSCode:**
   - Install "Remote - SSH" extension
   - Add to settings.json: `"remote.SSH.configFile": "~/.ssh/vscode/config"`
   - Set SSH timeout: `"remote.SSH.connectTimeout": 90`

4. **Connect:**
   - Open VSCode Remote Explorer → SSH Targets
   - Connect to `cloudx-{env}-{hostname}` (e.g., `cloudx-dev-myserver`)

**First connection takes 2-3 minutes (instance startup + VSCode server install). Subsequent connections are much faster (~30s).**

---

## Prerequisites

1. **Python 3.9+** - Required for cloudX-proxy and uv package manager
   - [Python Installation Guide](https://www.python.org/downloads/)
   - Check your version: `python --version` or `python3 --version`
   - Supports Python 3.9, 3.10, 3.11, 3.12+

2. **AWS CLI v2** - Used to configure AWS profiles and credentials
   - [Installation Guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
   - Required for `aws configure` during setup
   - Handles AWS credentials and region configuration

3. **AWS Session Manager Plugin** - Enables secure tunneling through AWS Systems Manager
   - [Installation Guide](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
   - Provides the secure connection channel
   - No need for public IP addresses or direct SSH access

4. **OpenSSH Client** - Handles SSH key management and connections
   - Windows: [Microsoft's OpenSSH Installation Guide](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse?tabs=gui)
   - macOS/Linux: Usually pre-installed
   - Manages SSH keys and configurations
   - Provides the SSH client for VSCode Remote

5. **uv** - Modern Python package installer and virtual environment manager
   ```bash
   pip install uv
   ```
   The `uvx` command from uv automatically:
   - Creates an isolated virtual environment for each package
   - Downloads and installs the package and its dependencies
   - Runs the package without explicit environment activation
   
   This means you can run cloudX-proxy directly with `uvx cloudx-proxy` without manually managing virtual environments or dependencies.

6. **VSCode with Remote SSH Extension** - Your development environment
   - Provides the integrated development environment
   - Uses the SSH configuration to connect to instances
   - Handles file synchronization and terminal sessions

## Installation

The cloudX-proxy package is available on PyPI and can run using uvx without explicit installation.

## Setup

cloudX-proxy includes a setup command that automates the entire configuration process:

```bash
# Basic setup with defaults (vscode profile and key)
uvx cloudx-proxy setup

# Setup with custom profile and key
uvx cloudx-proxy setup --profile myprofile --ssh-key mykey

# Setup with AWS environment
uvx cloudx-proxy setup --aws-env prod

# Setup with custom SSH config location
uvx cloudx-proxy setup --ssh-config ~/.ssh/cloudx/config

# Setup with 1Password integration
uvx cloudx-proxy setup --1password

# Setup with non-interactive automation
uvx cloudx-proxy setup --instance i-0123456789abcdef0 --hostname myserver --yes

# Combine options
uvx cloudx-proxy setup --profile myprofile --ssh-key mykey --ssh-config ~/.ssh/cloudx/config --1password --aws-env prod
```

The setup command will:

1. Configure AWS Profile:
   - Creates/validates AWS profile for IAM user in cloudX-{env}-{user} format
   - Supports AWS environment directories via --aws-env
   - Uses aws configure for credential input

2. Manage SSH Keys:
   - Creates new SSH key pair if needed
   - Fully supports 1Password integration:
     * Using 1Password SSH agent via `--1password` flag
     * Creates keys directly in 1Password's secure vault
     * Only public keys are exported to the filesystem
     * Follows SSH best practices using public keys to limit authentication attempts

3. Configure SSH:
   - Creates SSH configs with proper settings (default: ~/.ssh/vscode/config)
   - Custom config location can be specified with `--ssh-config`
   - Sets up optimized environment-specific configurations
   - Configures ProxyCommand with all necessary parameters
   - Ensures main ~/.ssh/config includes the configuration

4. Verify Instance Setup:
   - Checks instance setup status
   - Offers to wait for setup completion
   - Monitors setup progress

### SSH Configuration

The setup command configures SSH to use cloudX-proxy as a ProxyCommand, enabling seamless connections through AWS Systems Manager. For example, running:

```bash
uvx cloudx-proxy setup --profile myprofile --ssh-key mykey
```

Will create a three-tier configuration structure like this:

```
# Generic configuration (shared by all environments)
# Created by cloudx-proxy v1.0.0 on 2025-03-07 09:05:23
# Configuration type: generic
Host cloudx-*
    User ec2-user
    TCPKeepAlive yes
    ControlMaster auto
    ControlPath ~/.ssh/control/%r@%h:%p
    ControlPersist 4h

# Environment configuration (specific to a single environment)
# Created by cloudx-proxy v1.0.0 on 2025-03-07 09:05:23
# Configuration type: environment
Host cloudx-dev-*
    IdentityFile ~/.ssh/vscode/mykey
    IdentitiesOnly yes
    ProxyCommand uvx cloudx-proxy connect %h %p --profile myprofile --ssh-key mykey

# Host configuration (specific to a single instance)
# Created by cloudx-proxy v1.0.0 on 2025-03-07 09:05:23
# Configuration type: host
Host cloudx-dev-myserver
    HostName i-0123456789abcdef0
```

Allowing the user to:

```bash
ssh cloudx-dev-myserver
scp cloudx-dev-myserver:/path/to/file /local/path/to/file
```
without the need to provide any further credentials.

In these examples, ssh will use cloudx-proxy to connect to AWS with the `myprofile` credentials, allowing it to check the instance state and start the instance if it's stopped. Next cloudx-proxy will use `myprofile` to push the public part of the key `mykey` to the instance using SSM. Finally a tunnel is created between the local machine and the instance, using the SSM plugin, allowing SSH to connect to the instance using the private part of the `mykey` key. 

VSCode will be able to connect to the instance using the same SSH configuration.

### SSH Configuration Details
The setup command creates a hierarchical three-tier SSH configuration structure:

1. Generic configuration (cloudx-*) containing common settings shared across all environments:
   - User settings (ec2-user)
   - TCP keepalive for connection stability
   - SSH multiplexing for better performance (ControlMaster, ControlPath, ControlPersist)

2. Environment-specific configuration (cloudx-{env}-*) with:
   - Authentication settings (IdentityFile, IdentityAgent for 1Password)
   - ProxyCommand with environment-specific parameters
   - Inherits all settings from the generic configuration

3. Host-specific entries (cloudx-{env}-hostname) with:
   - Instance ID (HostName directive)
   - Inherits all settings from both generic and environment configurations

Each configuration tier is clearly marked with a timestamp and version information comment, making it easy to track when and how configurations were created.

When adding new instances to an existing environment, you can choose to:
- Keep the existing environment configuration if it's compatible
- Override the environment configuration with new settings
- Add host-specific settings only

This three-tier structure offers better maintainability by reducing duplication and making it clear which settings apply broadly and which are specific to an environment or host.

### Security Model: AWS and SSH Integration

cloudX-proxy implements a unique dual-layer security approach that combines AWS's robust authentication mechanisms with SSH's connection handling capabilities:

#### AWS Security Layer (Primary)
The primary security boundary is enforced through AWS Systems Manager (SSM) and EC2 Instance Connect. This layer provides:
- **Access Control**: Only authenticated AWS users with appropriate IAM permissions can establish SSM sessions
- **Dynamic Key Authorization**: EC2 Instance Connect allows temporary injection of SSH public keys, valid only for a single session
- **Network Security**: No inbound SSH ports need to be exposed, as all connections are established through AWS SSM's secure tunneling
- **Audit Trail**: All connection attempts and key pushes are logged in AWS CloudTrail

#### SSH Layer (Secondary)
SSH serves primarily as a connection handler rather than the main security mechanism:
- **Ephemeral Authentication**: The SSH key pair is used only to establish the connection through the SSM tunnel
- **Session Management**: SSH handles the actual terminal session, file transfers, and multiplexing
- **Key Flexibility**: Since keys are pushed dynamically for each session, the same key can safely be used across multiple instances
- **Zero Trust Model**: Even if a key is compromised, access still requires valid AWS credentials and permissions

This architecture means that:
1. The security of the connection relies primarily on AWS IAM permissions and SSM session management
2. SSH keys can be reused across instances without security implications
3. Each connection gets a fresh key authorization through EC2 Instance Connect
4. Instances remain completely closed to direct SSH access from the internet

### VSCode Configuration

After completing the setup, configure VSCode to use the SSH configuration created by cloudX-proxy:

1. **Install VSCode Extensions:**
   - Install the "Remote - SSH" extension from the VSCode marketplace
   - Optionally install "Remote Explorer" for better visualization

2. **Configure VSCode Settings:**
   Add these settings to your VSCode settings.json (Command Palette → "Preferences: Open Settings (JSON)"):
   ```json
   {
       "remote.SSH.configFile": "~/.ssh/vscode/config",
       "remote.SSH.connectTimeout": 90,
       "remote.SSH.serverInstallTimeout": 120,
       "remote.SSH.showLoginTerminal": true,
       "remote.SSH.remotePlatform": {
           "cloudx-*": "linux"
       }
   }
   ```

3. **Configuration Explanations:**
   - `configFile`: Points to the SSH config created by cloudX-proxy setup
   - `connectTimeout`: Extended timeout (90s) for instance startup and connection establishment
   - `serverInstallTimeout`: Additional time (120s) for VSCode server installation on first connect
   - `showLoginTerminal`: Shows connection progress for troubleshooting
   - `remotePlatform`: Tells VSCode that cloudx hosts are Linux systems

4. **Custom SSH Config Location:**
   If you used `--ssh-config` during setup, update the `configFile` path accordingly:
   ```json
   {
       "remote.SSH.configFile": "~/.ssh/cloudx/config"
   }
   ```

### How Connections Work

Understanding the connection flow helps with troubleshooting and explains why certain timeouts are necessary:

#### Step-by-Step Connection Process

1. **VSCode Initiates SSH Connection**
   - User clicks "Connect" or runs `ssh cloudx-{env}-{hostname}`
   - SSH reads the configuration and calls cloudX-proxy as ProxyCommand

2. **AWS Authentication & Instance Check**
   - cloudX-proxy authenticates using the specified AWS profile
   - Checks if the target EC2 instance exists and is accessible
   - Verifies SSM agent is installed and running on the instance

3. **Instance Startup (if needed)**
   - If instance is stopped, cloudX-proxy starts it automatically
   - Waits for instance to reach "running" state (typically 30-60 seconds)
   - Monitors SSM connectivity until agent responds

4. **SSH Key Distribution**
   - Reads the public SSH key from the local filesystem
   - Pushes the public key to the instance using EC2 Instance Connect
   - Key is temporarily authorized for the current session (60 seconds)

5. **SSM Tunnel Establishment**
   - Creates a secure tunnel through AWS Systems Manager
   - Port forwards local port to instance port 22 (SSH)
   - Tunnel handles all network traffic encryption

6. **SSH Connection Completion**
   - SSH client connects through the established tunnel
   - Authenticates using the private SSH key
   - VSCode completes the remote connection setup

#### Why Timeouts Are Important

- **Connect Timeout (90s)**: Accounts for instance startup + tunnel establishment
- **Server Install Timeout (120s)**: VSCode server download and installation on first connect
- **Instance startup can take 30-90 seconds** depending on instance type and size
- **Network conditions** may require additional time for AWS API calls

#### Connection Indicators

- **"Starting instance..."** - EC2 instance is being started
- **"Waiting for SSM connectivity..."** - Instance is starting, SSM agent not ready yet  
- **"Pushing SSH key..."** - Distributing public key via EC2 Instance Connect
- **"Starting session..."** - Creating SSM tunnel
- **VSCode "Installing server..."** - First-time setup of VSCode remote server

## Usage

### Command Line Options

#### Setup Command
```bash
uvx cloudx-proxy setup [OPTIONS]
```

Options:
- `--profile` (default: vscode): AWS profile to use. The profile's IAM user should follow the format cloudX-{env}-{user}. The environment part will be used as the default environment during setup.
- `--ssh-key` (default: vscode): Name of the SSH key to create/use. The key will be stored in the SSH config directory. This same name can be used in the connect command.
- `--ssh-config` (optional): Path to the SSH config file to use. If specified, configuration and keys will be stored in this location. Default is ~/.ssh/vscode/config.
- `--1password` (optional): Enable 1Password SSH agent integration. Can be used as a flag or with a vault name (e.g., `--1password Private`). First searches all vaults for existing keys with name "cloudX SSH Key - {keyname}". If no existing key found, creates new keys directly in the specified (or selected) 1Password vault and configures SSH to use the 1Password SSH agent. If a vault name is specified, that vault will be used for key storage; otherwise, prompts user to select from available vaults. By default, the "Private" vault is used when no vault specified. Note that only the "Private" vault is enabled for SSH by default in 1Password settings - other vaults must be manually enabled in 1Password SSH agent settings.
- `--aws-env` (optional): AWS environment directory to use. If specified, AWS configuration and credentials will be read from ~/.aws/aws-envs/{env}/.
- `--instance` (optional): EC2 instance ID to set up connection for. If provided, skips the instance ID prompt.
- `--hostname` (optional): Hostname to use for SSH configuration. If not provided, a hostname will be generated from the instance ID in non-interactive mode or prompted for in interactive mode.
- `--yes` (flag): Non-interactive mode, use default values for all prompts. Requires sufficient defaults or explicit parameters for all required values.

Example usage:
```bash
# Basic setup with defaults
uvx cloudx-proxy setup

# Setup with custom profile and key
uvx cloudx-proxy setup --profile myprofile --ssh-key mykey

# Setup with custom SSH config and 1Password integration (uses default "Private" vault)
uvx cloudx-proxy setup --ssh-config ~/.ssh/cloudx/config --1password

# Setup with 1Password integration using a specific vault
uvx cloudx-proxy setup --1password Work

# Complete setup with all options
uvx cloudx-proxy setup --profile myprofile --ssh-key mykey --ssh-config ~/.ssh/cloudx/config --1password --aws-env prod
```

#### Connect Command
```bash
uvx cloudx-proxy connect INSTANCE_ID [PORT] [OPTIONS]
```

Arguments:
- `INSTANCE_ID`: The EC2 instance ID to connect to (e.g., i-0123456789abcdef0)
- `PORT` (default: 22): The port to forward for SSH connection

Options:
- `--profile` (default: vscode): AWS profile to use. Should match the profile used in setup.
- `--ssh-key` (default: vscode): Name of the SSH key to use. Should match the key name used in setup.
- `--ssh-config` (optional): Path to the SSH config file to use. If provided during setup, should match here.
- `--region` (optional): AWS region to use. If not specified, uses the region from the AWS profile.
- `--aws-env` (optional): AWS environment directory to use. Should match the environment used in setup.

Example usage:
```bash
# Connect using defaults
uvx cloudx-proxy connect i-0123456789abcdef0

# Connect with custom profile and key
uvx cloudx-proxy connect i-0123456789abcdef0 22 --profile myprofile --ssh-key mykey

# Connect with custom port and region
uvx cloudx-proxy connect i-0123456789abcdef0 2222 --region us-east-1

# Connect with AWS environment
uvx cloudx-proxy connect i-0123456789abcdef0 22 --profile myprofile --aws-env prod
```

Note: The connect command is typically used through the SSH ProxyCommand configuration set up by the setup command. You rarely need to run it directly unless testing the connection.

#### List Command
```bash
uvx cloudx-proxy list [OPTIONS]
```

Options:
- `--ssh-config` (optional): Path to the SSH config file to use. If not specified, uses ~/.ssh/vscode/config.
- `--environment` (optional): Filter hosts by environment (e.g., dev, prod). If not specified, shows all environments.
- `--detailed` (flag): Show detailed information including instance IDs.

Example usage:
```bash
# List all configured hosts
uvx cloudx-proxy list

# List hosts in a specific environment
uvx cloudx-proxy list --environment dev

# List hosts with detailed information
uvx cloudx-proxy list --detailed

# List hosts from a custom SSH config
uvx cloudx-proxy list --ssh-config ~/.ssh/cloudx/config
```

The list command displays all configured cloudx-proxy hosts, grouped by environment. It provides a quick overview of available connections and can help troubleshoot SSH configuration issues.

### VSCode

1. Click the "Remote Explorer" icon in the VSCode sidebar
2. Select "SSH Targets" from the dropdown
3. Your configured hosts will appear (e.g., cloudx-dev)
4. Click the "+" icon next to a host to connect
5. VSCode will handle the rest, using cloudX-proxy to establish the connection

## AWS Permissions
### IAM User Permissions

The AWS IAM user has to be member of the AWS IAM Group that is created as part of the cloudX environment.
The group uses ABAC (Attribute Based Access Control) to allow access to the instances based on the tags.
The ABAC tag defaults to `cloudxuser` and should have the value of the username of the user that owns the instance.

Example:
- AWS IAM User `cloudx-dev-user1` is connecting to an instance with the tag `cloudxuser=cloudx-dev-user1`

Note: This user should be created using the cloudX-user product from Service Catalog in the AWS Console. This assures proper permissions and naming conventions. The user in the example is member of the `dev` group, part as part of the `cloudx-dev` environment.

The EC2 instance should have the tag `cloudxuser` with the value of the username of the user that is connecting to the instance. This is automatically set when the instance is created using the cloudX-instance product from Service Catalog in the AWS Console.

### EC2 Instance Permissions

The EC2 instance has a profile/role that provides enough permissions to allow the AWS SSM agent to connect to the instance, as well as
- CodeArtifact read only access, to use as a source for pip
- CodeCommit read only access, to pull code from the repository for installation
- Organizations read only access, to create aws sso configuration
- EC2 basic access, to allow the instance to introspect for tags and other metadata

These permissions are required to bootstrap the instance, so that after creation the instance can perform software installation and configuration without a user being present.

## Troubleshooting

### Common Issues

1. **Python/Installation Issues**
   - **Error: "python not found"** - Ensure Python 3.9+ is installed and in PATH
   - **Error: "uvx command not found"** - Install uv: `pip install uv`
   - **Error: "Package not found"** - Try updating uv: `pip install --upgrade uv`
   - **ImportError/ModuleNotFoundError** - Check Python version compatibility (`python --version`)

2. **Setup Issues**
   - If AWS profile validation fails, ensure your user ARN matches the cloudX-{env}-{user} format
   - For 1Password integration, ensure the CLI is installed and you're signed in
   - Check that ~/.ssh/vscode directory has proper permissions (700)
   - Verify main ~/.ssh/config is writable

2. **VSCode Connection Issues**
   - **Error: "Could not establish connection"** - Check VSCode SSH config file path in settings
   - **Error: "Host not found"** - Run `uvx cloudx-proxy list` to verify host configuration
   - **Timeout during connection** - Instance may be starting up (wait 2-3 minutes)
   - **"Installing server" hangs** - Increase `serverInstallTimeout` to 180+ seconds
   - **Connection works in terminal but not VSCode** - Verify `remote.SSH.configFile` setting

3. **Connection Timeout**
   - Ensure the instance has the SSM agent installed and running
   - Check that your AWS credentials have the required permissions
   - Verify the instance ID is correct
   - Increase the VSCode SSH timeout if needed
   - Check if the instance is starting up (can take several minutes)
   - **Region mismatch** - Ensure AWS profile region matches instance location

4. **SSH Key Issues**
   - If using 1Password SSH agent, verify agent is running (~/.1password/agent.sock exists)
   - Check file permissions (600 for private key, 644 for public key)
   - Verify the public key is being successfully pushed to the instance
   - For 1Password-managed keys, make sure:
     * 1Password CLI is installed and authenticated (`op account list` works)
     * SSH agent is enabled in 1Password settings
     * Keys are added to the SSH agent in 1Password
     * The key is visible with `op item list --categories "SSH Key"`
     * Keys follow the naming convention "cloudX SSH Key - {keyname}" for automatic discovery
     * If using a vault other than "Private", ensure that vault is enabled for SSH in 1Password settings
     * By default, only the "Private" vault is enabled for SSH in 1Password

5. **AWS CLI and Credentials Issues**
   - **Error: "aws command not found"** - Install AWS CLI v2 (not v1)
   - **Error: "Unable to locate credentials"** - Run `aws configure` to set up credentials
   - **Error: "Access Denied"** - Check IAM permissions and user ARN format
   - **Error: "Region not specified"** - Set default region in AWS profile or use `--region`
   - **Profile not found** - Verify profile exists: `aws configure list-profiles`
   - **Session token expired** - For SSO/temporary credentials, re-authenticate

6. **AWS Configuration**
   - Confirm AWS CLI is configured with valid credentials
   - Default region is eu-west-1 if not specified in profile or command line
   - If using AWS profile organizer, ensure your environment directory exists at `~/.aws/aws-envs/<environment>/`
   - Verify the Session Manager plugin is installed correctly
   - Check that the instance has the required IAM role for SSM

7. **Session Manager Plugin Issues**
   - **Error: "Session Manager plugin not found"** - Install the Session Manager plugin
   - **Error: "Invalid session"** - Check SSM agent status on instance: `sudo systemctl status amazon-ssm-agent`
   - **Plugin installation on macOS** - May need to add plugin to PATH manually
   - **Plugin installation on Windows** - Restart terminal after installation

8. **Instance Setup Status**
   - If setup appears stuck, check /home/ec2-user/.install-running exists
   - Verify /home/ec2-user/.install-done is created upon completion
   - Check instance system logs for setup script errors

### Diagnostic Commands

If you're experiencing issues, run these commands to gather diagnostic information:

```bash
# Check Python and uv versions
python --version
uvx --version

# Verify AWS CLI and credentials
aws --version
aws sts get-caller-identity --profile your-profile

# Test Session Manager plugin
aws ssm start-session --target i-1234567890abcdef0 --profile your-profile

# List configured SSH hosts
uvx cloudx-proxy list --detailed

# Test direct connection (replace with your values)
uvx cloudx-proxy connect i-1234567890abcdef0 22 --profile your-profile
```

## License

MIT License - see LICENSE file for details
