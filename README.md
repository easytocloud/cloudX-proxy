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

## AWS Credentials Setup

The proxy expects to find AWS credentials in a profile named 'vscode' by default. These credentials should be the Access Key and Secret Key that were created by deploying the cloudX-user stack in your AWS account. The cloudX-user stack creates an IAM user with the minimal permissions required for:
- Starting/stopping EC2 instances
- Establishing SSM sessions
- Pushing SSH keys via EC2 Instance Connect

The proxy supports easytocloud's AWS profile organizer for managing multiple AWS environments. You can store your AWS configuration and credentials in `~/.aws/aws-envs/<environment>` directories and use the `--aws-env` option to specify which environment to use.

## Setup

cloudX-proxy includes a setup command that automates the entire configuration process:

```bash
# Basic setup with defaults (vscode profile and key)
uvx cloudx-proxy setup

# Setup with custom profile and key
uvx cloudx-proxy setup --profile myprofile --ssh-key mykey

# Setup with AWS environment
uvx cloudx-proxy setup --aws-env prod
```

The setup command will:

1. Configure AWS Profile:
   - Creates/validates AWS profile with cloudX-{env}-{user} format
   - Supports AWS environment directories via --aws-env
   - Uses aws configure for credential input

2. Manage SSH Keys:
   - Creates new SSH key pair if needed
   - Offers 1Password integration options:
     * Using 1Password SSH agent
     * Storing private key as 1Password document

3. Configure SSH:
   - Creates ~/.ssh/vscode/config with proper settings
   - Sets up environment-specific configurations
   - Configures ProxyCommand with all necessary parameters
   - Ensures main ~/.ssh/config includes the configuration

4. Verify Instance Setup:
   - Checks instance setup status
   - Offers to wait for setup completion
   - Monitors setup progress

### SSH Configuration

The setup command configures SSH to use cloudX-proxy as a ProxyCommand, enabling seamless connections through AWS Systems Manager. It creates:

1. A base configuration for each environment (cloudx-{env}-*) with:
   - User and key settings
   - 1Password integration if selected
   - ProxyCommand with appropriate parameters

2. Individual host entries for each instance:
   - Uses consistent naming (cloudx-{env}-hostname)
   - Maps to instance IDs automatically
   - Inherits environment-level settings

When adding new instances to an existing environment, you can choose to:
- Override the environment configuration with new settings
- Add instance-specific settings while preserving the environment config

### VSCode Configuration

1. Install the "Remote - SSH" extension in VSCode
2. Configure VSCode settings:
   ```json
   {
       "remote.SSH.configFile": "~/.ssh/vscode/config",
       "remote.SSH.connectTimeout": 90
   }
   ```

## Usage

### Command Line Options

#### Setup Command
```bash
uvx cloudx-proxy setup [OPTIONS]
```

Options:
- `--profile` (default: vscode): AWS profile to use. The profile's IAM user should follow the format cloudX-{env}-{user}. The environment part will be used as the default environment during setup.
- `--ssh-key` (default: vscode): Name of the SSH key to create/use. The key will be stored in ~/.ssh/vscode/{name}. This same name can be used in the connect command.
- `--aws-env` (optional): AWS environment directory to use. If specified, AWS configuration and credentials will be read from ~/.aws/aws-envs/{env}/.

Example usage:
```bash
# Basic setup with defaults
uvx cloudx-proxy setup

# Setup with custom profile and key
uvx cloudx-proxy setup --profile myprofile --ssh-key mykey

# Setup with AWS environment
uvx cloudx-proxy setup --profile myprofile --aws-env prod
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

The AWS user needs these permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:StartInstances",
                "ec2:DescribeInstances",
                "ssm:StartSession",
                "ssm:DescribeInstanceInformation",
                "ec2-instance-connect:SendSSHPublicKey"
            ],
            "Resource": "*"
        }
    ]
}
```
Note: This user should be created using the cloudX-user product from Service Catalog in the AWS Console. This assures proper permissions and naming conventions.

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

3. **SSH Key Issues**
   - If using 1Password SSH agent, verify agent is running (~/.1password/agent.sock exists)
   - Check file permissions (600 for private key, 644 for public key)
   - Verify the public key is being successfully pushed to the instance
   - For stored keys in 1Password, ensure you can access them via the CLI

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
