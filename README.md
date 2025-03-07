# cloudX-proxy

A cross-platform SSH proxy command for connecting VSCode to CloudX/Cloud9 EC2 instances using AWS Systems Manager Session Manager.

## Overview

cloudX-proxy enables seamless SSH connections from VSCode to EC2 instances using AWS Systems Manager Session Manager, eliminating the need for direct SSH access or public IP addresses. It handles:

- Automatic instance startup if stopped
- SSH key distribution via EC2 Instance Connect
- SSH tunneling through AWS Systems Manager
- Cross-platform support (Windows, macOS, Linux)

## Prerequisites

1. **AWS CLI v2** - Used to configure AWS profiles and credentials
   - [Installation Guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
   - Required for `aws configure` during setup
   - Handles AWS credentials and region configuration

2. **AWS Session Manager Plugin** - Enables secure tunneling through AWS Systems Manager
   - [Installation Guide](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
   - Provides the secure connection channel
   - No need for public IP addresses or direct SSH access

3. **OpenSSH Client** - Handles SSH key management and connections
   - Windows: [Microsoft's OpenSSH Installation Guide](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse?tabs=gui)
   - macOS/Linux: Usually pre-installed
   - Manages SSH keys and configurations
   - Provides the SSH client for VSCode Remote

4. **uv** - Modern Python package installer and virtual environment manager
   ```bash
   pip install uv
   ```
   The `uvx` command from uv automatically:
   - Creates an isolated virtual environment for each package
   - Downloads and installs the package and its dependencies
   - Runs the package without explicit environment activation
   
   This means you can run cloudX-proxy directly with `uvx cloudx-proxy` without manually managing virtual environments or dependencies.

5. **VSCode with Remote SSH Extension** - Your development environment
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

1. Install the "Remote - SSH" extension in VSCode
2. Configure VSCode settings:
   ```json
   {
       "remote.SSH.configFile": "~/.ssh/vscode/config",
       "remote.SSH.connectTimeout": 90
   }
   ```
This extra long timeout is necessary to account for the time it takes to start the instance and establish the connection.
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
- `--1password` (flag): Enable 1Password SSH agent integration. Creates keys directly in 1Password and configures SSH to use the 1Password SSH agent.
- `--aws-env` (optional): AWS environment directory to use. If specified, AWS configuration and credentials will be read from ~/.aws/aws-envs/{env}/.

Example usage:
```bash
# Basic setup with defaults
uvx cloudx-proxy setup

# Setup with custom profile and key
uvx cloudx-proxy setup --profile myprofile --ssh-key mykey

# Setup with custom SSH config and 1Password integration
uvx cloudx-proxy setup --ssh-config ~/.ssh/cloudx/config --1password

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

1. **Setup Issues**
   - If AWS profile validation fails, ensure your user ARN matches the cloudX-{env}-{user} format
   - For 1Password integration, ensure the CLI is installed and you're signed in
   - Check that ~/.ssh/vscode directory has proper permissions (700)
   - Verify main ~/.ssh/config is writable

2. **Connection Timeout**
   - Ensure the instance has the SSM agent installed and running
   - Check that your AWS credentials have the required permissions
   - Verify the instance ID is correct
   - Increase the VSCode SSH timeout if needed
   - Check if the instance is starting up (can take several minutes)

3. **SSH Key Issues**
   - If using 1Password SSH agent, verify agent is running (~/.1password/agent.sock exists)
   - Check file permissions (600 for private key, 644 for public key)
   - Verify the public key is being successfully pushed to the instance
   - For 1Password-managed keys, make sure:
     * 1Password CLI is installed and authenticated (`op account list` works)
     * SSH agent is enabled in 1Password settings
     * Keys are added to the SSH agent in 1Password
     * The key is visible with `op item list --categories "SSH Key"`

4. **AWS Configuration**
   - Confirm AWS CLI is configured with valid credentials
   - Default region is eu-west-1 if not specified in profile or command line
   - If using AWS profile organizer, ensure your environment directory exists at `~/.aws/aws-envs/<environment>/`
   - Verify the Session Manager plugin is installed correctly
   - Check that the instance has the required IAM role for SSM

5. **Instance Setup Status**
   - If setup appears stuck, check /home/ec2-user/.install-running exists
   - Verify /home/ec2-user/.install-done is created upon completion
   - Check instance system logs for setup script errors

## License

MIT License - see LICENSE file for details
