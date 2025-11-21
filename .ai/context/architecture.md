# Architecture

## Core Components

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

- **`setup.py`**: `CloudXSetup` class that implements a comprehensive setup wizard with three-tier SSH configuration.

## CloudX Environment Context

CloudX is a development environment consisting of:
- A local VSCode installation
- A remote development server (EC2 instance) running with auto-shutdown

The AWS side consists of:
- **CloudX-environment**: Defines resources (VPC subnet) where instances are launched.
- **CloudX-user**: IAM user with permissions to manage their CloudX-instance(s) based on ABAC tags.
- **CloudX-instance**: EC2 instance that automatically stops after inactivity.

## SSH Configuration Structure

CloudX-proxy uses a hierarchical three-tier SSH configuration approach to minimize duplication:

1. **Generic Configuration (`cloudX-*`)**: Common settings for all environments
   - User settings (`ec2-user`)
   - TCP keepalive
   - SSH multiplexing configuration (`ControlMaster`, `ControlPath`, `ControlPersist`)

2. **Environment Configuration (`cloudX-{env}-*`)**: Environment-specific settings
   - Authentication configuration (identity settings)
   - `ProxyCommand` with environment-specific parameters

3. **Host Configuration (`cloudX-{env}-hostname`)**: Instance-specific settings
   - `HostName` (instance ID)
   - Optional overrides for incompatible settings

## Security Model

The application implements a dual-layer security approach:

### 1. AWS Security Layer (Primary)
Enforced through AWS IAM via Systems Manager (SSM) and EC2 Instance Connect:
- **Access Control**: Only authenticated AWS users with appropriate IAM permissions can establish SSM sessions.
- **Dynamic Key Authorization**: EC2 Instance Connect allows temporary injection of SSH public keys (valid for 60s).
- **Network Security**: No inbound SSH ports exposed; all connections use AWS SSM's secure tunneling.
- **Audit Trail**: All connection attempts and key pushes are logged in AWS CloudTrail.

### 2. SSH Layer (Secondary)
Acts as a connection handler:
- **Ephemeral Authentication**: SSH key pair used only to establish connection through SSM tunnel.
- **Session Management**: Handles terminal session, file transfers, and multiplexing.
- **Key Flexibility**: Keys can be reused across instances; each connection gets fresh authorization.

## Connection Flow

1. **VSCode Initiates SSH Connection**: User connects to `cloudX-{env}-{hostname}`.
2. **AWS Authentication & Instance Check**: `cloudX-proxy` authenticates and checks instance status.
3. **Instance Startup**: If stopped, instance is started (waits for "running" state).
4. **SSH Key Distribution**: Public key pushed to instance via EC2 Instance Connect.
5. **SSM Tunnel Establishment**: Secure tunnel created via AWS Systems Manager.
6. **SSH Connection Completion**: SSH client connects through tunnel using private key.

## Operating Modes

- **Setup Mode**: Establishes config files and directories.
    - Configures AWS profile (default 'vscode').
    - Manages SSH keys (default 'vscode').
    - Generates SSH config entries.
    - Supports 1Password integration.
- **Connect Mode**: Establishes the actual connection.
    - Used internally as a `ProxyCommand`.
    - Runs using `uvx`.

## AWS Permissions

### IAM User/Role Permissions
Requires permissions for:
- `ssm:DescribeInstanceInformation`
- `ec2:StartInstances`
- `ssm:StartSession` (for instance and document `AWS-StartSSHSession`)
- `ec2-instance-connect:SendSSHPublicKey`

### EC2 Instance Permissions
Instance profile requires permissions for:
- SSM agent connectivity
- CodeArtifact (read-only)
- CodeCommit (read-only)
- Organizations (read-only)
- EC2 basic access (tags/metadata)