# cloudX-client

A cross-platform Python client for connecting VSCode to CloudX/Cloud9 EC2 instances via SSH over AWS Systems Manager Session Manager.

## Overview

cloudX-client enables seamless SSH connections from VSCode to EC2 instances using AWS Systems Manager Session Manager, eliminating the need for direct SSH access or public IP addresses. It handles:

- Automatic instance startup if stopped
- SSH key distribution via EC2 Instance Connect
- SSH tunneling through AWS Systems Manager
- Cross-platform support (Windows, macOS, Linux)

## Prerequisites

1. **AWS CLI v2** - [Installation Guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
2. **AWS Session Manager Plugin** - [Installation Guide](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
3. **OpenSSH Client**
   - Windows: [Microsoft's OpenSSH Installation Guide](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse?tabs=gui)
   - macOS/Linux: Usually pre-installed
4. **uv** - Python package installer and resolver
   ```bash
   pip install uv
   ```
5. **VSCode with Remote SSH Extension** installed

## AWS Credentials Setup

The client expects to find AWS credentials in a profile named 'vscode' by default. These credentials should be the Access Key and Secret Key that were created by deploying the cloudX-user stack in your AWS account. The cloudX-user stack creates an IAM user with the minimal permissions required for:
- Starting/stopping EC2 instances
- Establishing SSM sessions
- Pushing SSH keys via EC2 Instance Connect

Once the SSH session is established, the user has to further configure the instance using `generate-sso-config` tool. This is a one-time setup unless the user's access to AWS accounts changes, in which case the user should re-run the `generate-sso-config` tool.

It is recommended to use  --generate-directories and --use-ou-structure to create working directories for each account the user has access to.

Everytime the user connects to the instance, `ssostart` will authenticate the user with AWS SSO and generate temporary credentials. 

This ensures you have the appropriate AWS access both for connecting to the instance and for working within it.

The client also supports easytocloud's AWS profile organizer. If you use multiple AWS environments, you can store your AWS configuration and credentials in `~/.aws/aws-envs/<environment>` directories and use the `--aws-env` option to specify which environment to use.

## Setup

1. Deploy the cloudX-user stack in your AWS account to create the necessary IAM user
2. Configure the 'vscode' AWS profile with the credentials from the cloudX-user stack
3. Install uv if you haven't already:
   ```bash
   pip install uv
   ```

The `uvx` command, part of the uv package manager, makes running cloudx-client seamless. When you run `uvx cloudx-client`, it automatically:
- Pulls the latest version from PyPI
- Creates an isolated virtual environment
- Installs all dependencies
- Runs the code

All of this happens in a single, fast operation without any manual setup required.

## SSH Configuration

### 1. Generate SSH Key Pair

If you don't already have an SSH key pair for VSCode:

```bash
# Create .ssh/vscode directory
mkdir -p ~/.ssh/vscode

# Generate key pair
ssh-keygen -t rsa -b 4096 -f ~/.ssh/vscode/vscode
```

### 2. Configure SSH

#### Unix-like Systems (macOS/Linux)

1. Create or edit `~/.ssh/config`:
   ```bash
   # Include VSCode-specific config
   Include vscode/config
   ```

2. Create `~/.ssh/vscode/config`:
   ```
   Host cloudx-*
       ProxyCommand uvx cloudx-client %h %p
       User ec2-user
       IdentityFile ~/.ssh/vscode/vscode
       StrictHostKeyChecking no
       UserKnownHostsFile /dev/null

   # Example host configuration
   Host cloudx-dev
       HostName i-0123456789abcdef0  # Your EC2 instance ID
   ```

#### Windows

1. Create or edit `%USERPROFILE%\.ssh\config`:
   ```
   Include vscode/config
   ```

2. Create `%USERPROFILE%\.ssh\vscode\config`:
   ```
   Host cloudx-*
       ProxyCommand uvx cloudx-client %h %p
       User ec2-user
       IdentityFile %USERPROFILE%\.ssh\vscode\vscode
       StrictHostKeyChecking no
       UserKnownHostsFile /dev/null

   # Example host configuration
   Host cloudx-dev
       HostName i-0123456789abcdef0  # Your EC2 instance ID
   ```

### 3. VSCode Configuration

1. Install the "Remote - SSH" extension in VSCode
2. Configure VSCode settings:
   ```json
   {
       "remote.SSH.configFile": "~/.ssh/vscode/config",
       "remote.SSH.connectTimeout": 90
   }
   ```

## Usage

### Command Line

```bash
# Basic usage (uses default vscode profile, port 22, and eu-west-1 region)
uvx cloudx-client i-0123456789abcdef0

# With custom port
uvx cloudx-client i-0123456789abcdef0 2222

# With custom profile
uvx cloudx-client i-0123456789abcdef0 --profile myprofile

# With different region (overrides eu-west-1 default)
uvx cloudx-client i-0123456789abcdef0 --region us-east-1

# With AWS profile organizer environment
uvx cloudx-client i-0123456789abcdef0 --aws-env prod

# With custom SSH key
uvx cloudx-client i-0123456789abcdef0 --key-path ~/.ssh/custom_key.pub
```

### VSCode

1. Click the "Remote Explorer" icon in the VSCode sidebar
2. Select "SSH Targets" from the dropdown
3. Your configured hosts will appear (e.g., cloudx-dev)
4. Click the "+" icon next to a host to connect
5. VSCode will handle the rest, using cloudX-client to establish the connection

## AWS Permissions

The AWS user/role needs these permissions:

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

## Troubleshooting

1. **Connection Timeout**
   - Ensure the instance has the SSM agent installed and running
   - Check that your AWS credentials have the required permissions
   - Verify the instance ID is correct
   - Increase the VSCode SSH timeout if needed

2. **SSH Key Issues**
   - Ensure the key pair exists in the correct location
   - Check file permissions (600 for private key, 644 for public key)
   - Verify the public key is being successfully pushed to the instance

3. **AWS Configuration**
   - Confirm AWS CLI is configured with valid credentials (default profile name is 'vscode')
   - Default region is eu-west-1 if not specified in profile or command line
   - If using AWS profile organizer, ensure your environment directory exists at `~/.aws/aws-envs/<environment>/`
   - Verify the Session Manager plugin is installed correctly
   - Check that the instance has the required IAM role for SSM

## License

MIT License - see LICENSE file for details
