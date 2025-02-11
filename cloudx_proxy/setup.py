import os
import time
import json
import subprocess
import platform
from pathlib import Path
from typing import Optional, Tuple
import boto3
from botocore.exceptions import ClientError

class CloudXSetup:
    def __init__(self, profile: str = "vscode", ssh_key: str = "vscode", aws_env: str = None):
        """Initialize cloudx-proxy setup.
        
        Args:
            profile: AWS profile name (default: "vscode")
            ssh_key: SSH key name (default: "vscode")
            aws_env: AWS environment directory (default: None)
        """
        self.profile = profile
        self.ssh_key = ssh_key
        self.aws_env = aws_env
        self.home_dir = str(Path.home())
        self.ssh_dir = Path(self.home_dir) / ".ssh" / "vscode"
        self.ssh_config_file = self.ssh_dir / "config"
        self.ssh_key_file = self.ssh_dir / f"{ssh_key}"
        self.default_env = None

    def print_header(self, text: str) -> None:
        """Print a section header.
        
        Args:
            text: The header text
        """
        print(f"\n\n\033[1;94m=== {text} ===\033[0m")

    def print_status(self, message: str, status: bool = None, indent: int = 0) -> None:
        """Print a status message with optional checkmark/cross.
        
        Args:
            message: The message to print
            status: True for success (✓), False for failure (✗), None for no symbol
            indent: Number of spaces to indent
        """
        prefix = " " * indent
        if status is not None:
            symbol = "✓" if status else "✗"
            color = "\033[92m" if status else "\033[91m"  # Green for success, red for failure
            reset = "\033[0m"
            print(f"{prefix}{color}{symbol}{reset} {message}")
        else:
            print(f"{prefix}○ {message}")

    def prompt(self, message: str, default: str = None) -> str:
        """Display a colored prompt for user input.
        
        Args:
            message: The prompt message
            default: Default value (shown in brackets)
        
        Returns:
            str: User's input or default value
        """
        if default:
            prompt_text = f"\033[93m{message} [{default}]: \033[0m"
        else:
            prompt_text = f"\033[93m{message}: \033[0m"
        response = input(prompt_text)
        return response if response else default

    def setup_aws_profile(self) -> bool:
        """Set up AWS profile using aws configure command.
        
        Returns:
            bool: True if profile was set up successfully or user chose to continue
        """
        self.print_status("Checking AWS profile configuration...")
        
        try:
            # Configure AWS environment if specified
            if self.aws_env:
                aws_env_dir = os.path.expanduser(f"~/.aws/aws-envs/{self.aws_env}")
                os.environ["AWS_CONFIG_FILE"] = os.path.join(aws_env_dir, "config")
                os.environ["AWS_SHARED_CREDENTIALS_FILE"] = os.path.join(aws_env_dir, "credentials")

            # Try to create session with profile
            try:
                session = boto3.Session(profile_name=self.profile)
            except:
                # Profile doesn't exist, create it
                self.print_status(f"AWS profile '{self.profile}' not found", False, 2)
                self.print_status("Setting up AWS profile...", None, 2)
                print("\033[96mPlease enter your AWS credentials:\033[0m")
                
                # Use aws configure command
                subprocess.run([
                    'aws', 'configure',
                    '--profile', self.profile
                ], check=True)
                
                # Create new session with configured profile
                session = boto3.Session(profile_name=self.profile)

            # Verify the profile works
            try:
                identity = session.client('sts').get_caller_identity()
                user_arn = identity['Arn']
                
                # Extract environment from IAM user name
                user_parts = [part for part in user_arn.split('/') if part.startswith('cloudX-')]
                if user_parts:
                    self.default_env = user_parts[0].split('-')[1]  # Extract env from cloudX-{env}-{user}
                    self.print_status(f"AWS profile '{self.profile}' exists and matches cloudX format", True, 2)
                    return True
                else:
                    self.print_status(f"AWS profile exists but doesn't match cloudX-{{env}}-{{user}} format", False, 2)
                    self.print_status("Please ensure your IAM user follows the format: cloudX-{env}-{username}", None, 2)
                    return False
            except ClientError:
                self.print_status("Invalid AWS credentials", False, 2)
                return False

        except Exception as e:
            self.print_status(f"\033[1;91mError:\033[0m {str(e)}", False, 2)
            return False

    def setup_ssh_key(self) -> bool:
        """Set up SSH key pair.
        
        Returns:
            bool: True if key was set up successfully
        """
        self.print_header("SSH Key Configuration")
        self.print_status(f"Checking SSH key '{self.ssh_key}' configuration...")
        
        try:
            # Create .ssh/vscode directory if it doesn't exist
            self.ssh_dir.mkdir(parents=True, exist_ok=True)
            self.print_status("SSH directory exists", True, 2)
            
            key_exists = self.ssh_key_file.exists() and (self.ssh_key_file.with_suffix('.pub')).exists()
            
            if key_exists:
                self.print_status(f"SSH key '{self.ssh_key}' exists", True, 2)
            else:
                self.print_status(f"Generating new SSH key '{self.ssh_key}'...", None, 2)
                subprocess.run([
                    'ssh-keygen',
                    '-t', 'ed25519',
                    '-f', str(self.ssh_key_file),
                    '-N', ''  # Empty passphrase
                ], check=True)
                self.print_status("SSH key generated", True, 2)
                
            
            return True

        except Exception as e:
            self.print_status(f"Error: {str(e)}", False, 2)
            continue_setup = self.prompt("Would you like to continue anyway?", "Y").lower() != 'n'
            if continue_setup:
                self.print_status("Continuing setup despite SSH key issues", None, 2)
                return True
            return False

    def _add_host_entry(self, cloudx_env: str, instance_id: str, hostname: str, current_config: str) -> bool:
        """Add settings to a specific host entry.
        
        Args:
            cloudx_env: CloudX environment
            instance_id: EC2 instance ID
            hostname: Hostname for the instance
            current_config: Current SSH config content
        
        Returns:
            bool: True if settings were added successfully
        """
        try:
            # Build host entry with all settings
            proxy_command = "uvx cloudx-proxy connect %h %p"
            if self.profile != "vscode":
                proxy_command += f" --profile {self.profile}"
            if self.aws_env:
                proxy_command += f" --aws-env {self.aws_env}"
            if self.ssh_key != "vscode":
                proxy_command += f" --ssh-key {self.ssh_key}"

            host_entry = f"""
Host cloudx-{cloudx_env}-{hostname}
    HostName {instance_id}
    User ec2-user
"""
            host_entry += f"""    IdentityFile {self.ssh_key_file}
    IdentitiesOnly yes
"""
            host_entry += f"""    ProxyCommand {proxy_command}
"""
            
            # Append host entry
            with open(self.ssh_config_file, 'a') as f:
                f.write(host_entry)
            self.print_status("Host entry added with settings", True, 2)
            return True

        except Exception as e:
            self.print_status(f"\033[1;91mError:\033[0m {str(e)}", False, 2)
            continue_setup = self.prompt("Would you like to continue anyway?", "Y").lower() != 'n'
            if continue_setup:
                self.print_status("Continuing setup despite SSH config issues", None, 2)
                return True
            return False

    def setup_ssh_config(self, cloudx_env: str, instance_id: str, hostname: str) -> bool:
        """Set up SSH config for the instance.
        
        This method manages the SSH configuration in ~/.ssh/vscode/config, with the following behavior:
        1. For a new environment (if cloudx-{env}-* doesn't exist):
           Creates a base config with:
           - User and key configuration
           - 1Password SSH agent integration if selected
           - ProxyCommand using uvx cloudx-proxy with proper parameters
        
        2. For an existing environment:
           - Skips creating duplicate environment config
           - Only adds the new host entry
        
        Example config structure:
        ```
        # Base environment config (created only once per environment)
        Host cloudx-{env}-*
            User ec2-user
            IdentityAgent ~/.1password/agent.sock  # If using 1Password
            IdentityFile ~/.ssh/vscode/key.pub    # .pub for 1Password, no .pub otherwise
            IdentitiesOnly yes                    # If using 1Password
            ProxyCommand uvx cloudx-proxy connect %h %p --profile profile --aws-env env
        
        # Host entries (added for each instance)
        Host cloudx-{env}-hostname
            HostName i-1234567890
        ```
        
        Args:
            cloudx_env: CloudX environment (e.g., dev, prod)
            instance_id: EC2 instance ID
            hostname: Hostname for the instance
        
        Returns:
            bool: True if config was set up successfully
        """
        self.print_header("SSH Configuration")
        self.print_status("Setting up SSH configuration...")
        
        try:
            # Check existing configuration
            if self.ssh_config_file.exists():
                current_config = self.ssh_config_file.read_text()
                # Check if configuration for this environment already exists
                if f"Host cloudx-{cloudx_env}-*" in current_config:
                    self.print_status(f"Found existing config for cloudx-{cloudx_env}-*", True, 2)
                    choice = self.prompt(
                        "Would you like to (1) override the existing config or "
                        "(2) add settings to the specific host entry?",
                        "1"
                    )
                    if choice == "2":
                        # Add settings to specific host entry
                        self.print_status("Adding settings to specific host entry", None, 2)
                        return self._add_host_entry(cloudx_env, instance_id, hostname, current_config)
                    else:
                        # Remove existing config for this environment
                        self.print_status("Removing existing configuration", None, 2)
                        lines = current_config.splitlines()
                        new_lines = []
                        skip = False
                        for line in lines:
                            if line.strip() == f"Host cloudx-{cloudx_env}-*":
                                skip = True
                            elif skip and line.startswith("Host "):
                                skip = False
                            if not skip:
                                new_lines.append(line)
                        current_config = "\n".join(new_lines)
                        with open(self.ssh_config_file, 'w') as f:
                            f.write(current_config)

            # Create base config
            self.print_status(f"Creating new config for cloudx-{cloudx_env}-*", None, 2)
            # Build ProxyCommand with only non-default parameters
            proxy_command = "uvx cloudx-proxy connect %h %p"
            if self.profile != "vscode":
                proxy_command += f" --profile {self.profile}"
            if self.aws_env:
                proxy_command += f" --aws-env {self.aws_env}"
            if self.ssh_key != "vscode":
                proxy_command += f" --ssh-key {self.ssh_key}"

            # Build base configuration
            base_config = f"""# cloudx-proxy SSH Configuration
Host cloudx-{cloudx_env}-*
    User ec2-user
"""
            # Add key configuration
            base_config += f"""    IdentityFile {self.ssh_key_file}
    IdentitiesOnly yes

"""
            # Add ProxyCommand
            base_config += f"""    ProxyCommand {proxy_command}
"""
            
            # If file exists, append the new config, otherwise create it
            if self.ssh_config_file.exists():
                with open(self.ssh_config_file, 'a') as f:
                    f.write("\n" + base_config)
            else:
                self.ssh_config_file.write_text(base_config)
            self.print_status("Base configuration created", True, 2)

            # Add specific host entry
            self.print_status(f"Adding host entry for cloudx-{cloudx_env}-{hostname}", None, 2)
            host_entry = f"""
Host cloudx-{cloudx_env}-{hostname}
    HostName {instance_id}
"""
            with open(self.ssh_config_file, 'a') as f:
                f.write(host_entry)
            self.print_status("Host entry added", True, 2)

            # Ensure main SSH config includes our config
            main_config = Path(self.home_dir) / ".ssh" / "config"
            include_line = f"Include {self.ssh_config_file}\n"
            
            if main_config.exists():
                content = main_config.read_text()
                if include_line not in content:
                    with open(main_config, 'a') as f:
                        f.write(f"\n{include_line}")
                    self.print_status("Added include line to main SSH config", True, 2)
                else:
                    self.print_status("Main SSH config already includes our config", True, 2)
            else:
                main_config.write_text(include_line)
                self.print_status("Created main SSH config with include line", True, 2)

            self.print_status("\nSSH configuration summary:", None)
            self.print_status(f"Main config: {main_config}", None, 2)
            self.print_status(f"cloudx-proxy config: {self.ssh_config_file}", None, 2)
            self.print_status(f"Connect using: ssh cloudx-{cloudx_env}-{hostname}", None, 2)
            
            return True

        except Exception as e:
            self.print_status(f"\033[1;91mError:\033[0m {str(e)}", False, 2)
            continue_setup = self.prompt("Would you like to continue anyway?", "Y").lower() != 'n'
            if continue_setup:
                self.print_status("Continuing setup despite SSH config issues", None, 2)
                return True
            return False

    def check_instance_setup(self, instance_id: str) -> Tuple[bool, bool, bool]:
        """Check if instance setup is complete.
        
        Args:
            instance_id: EC2 instance ID
        
        Returns:
            Tuple[bool, bool, bool]: (ssm_accessible, is_running, is_setup_complete)
        """
        try:
            session = boto3.Session(profile_name=self.profile)
            ssm = session.client('ssm')
            ec2 = session.client('ec2')
            
            # First check if instance exists and its power state
            try:
                response = ec2.describe_instances(InstanceIds=[instance_id])
                if not response['Reservations']:
                    self.print_status("Instance not found", False, 4)
                    return False, False, False
                
                instance = response['Reservations'][0]['Instances'][0]
                state = instance['State']['Name']
                
                if state != 'running':
                    self.print_status(f"Instance is {state}", False, 4)
                    return True, False, False
            except Exception as e:
                self.print_status(f"Error checking instance state: {e}", False, 4)
                return False, False, False
            
            # Now check SSM connectivity
            try:
                self.print_status("Checking SSM connectivity...", None, 4)
                response = ssm.describe_instance_information(
                    Filters=[{'Key': 'InstanceIds', 'Values': [instance_id]}]
                )
                if not response['InstanceInformationList']:
                    self.print_status("Instance is running but not yet accessible via SSM", False, 4)
                    self.print_status("This is normal if the instance is still configuring", None, 4)
                    return True, True, False
                
                self.print_status("SSM connection established", True, 4)
                
                # Check setup status using SSM command
                self.print_status("Checking setup status...", None, 4)
                response = ssm.send_command(
                    InstanceIds=[instance_id],
                    DocumentName='AWS-RunShellScript',
                    Parameters={
                        'commands': [
                            'test -f /home/ec2-user/.install-done && echo "DONE" || '
                            'test -f /home/ec2-user/.install-running && echo "RUNNING" || '
                            'echo "NOT_STARTED"'
                        ]
                    }
                )
                
                command_id = response['Command']['CommandId']
                
                # Wait for command completion
                for _ in range(10):  # 10 second timeout
                    time.sleep(1)
                    result = ssm.get_command_invocation(
                        CommandId=command_id,
                        InstanceId=instance_id
                    )
                    if result['Status'] in ['Success', 'Failed']:
                        break
                
                is_setup_complete = result['Status'] == 'Success' and result['StandardOutputContent'].strip() == 'DONE'
                
                if is_setup_complete:
                    self.print_status("Setup is complete", True, 4)
                else:
                    status = result['StandardOutputContent'].strip()
                    self.print_status(f"Setup status: {status}", None, 4)
                
                return True, True, is_setup_complete
                
            except Exception as e:
                self.print_status(f"Error checking SSM status: {e}", False, 4)
                return False, True, False

        except Exception as e:
            self.print_status(f"\033[1;91mError:\033[0m {str(e)}", False, 4)
            return False, False, False

    def wait_for_setup_completion(self, instance_id: str) -> bool:
        """Wait for instance setup to complete.
        
        Args:
            instance_id: EC2 instance ID
        
        Returns:
            bool: True if setup completed successfully or user chose to continue
        """
        self.print_header("Instance Setup Check")
        self.print_status(f"Checking instance {instance_id} status...")
        
        ssm_accessible, is_running, is_complete = self.check_instance_setup(instance_id)
        
        if not ssm_accessible and not is_running:
            continue_setup = self.prompt("Would you like to continue anyway?", "Y").lower() != 'n'
            if continue_setup:
                self.print_status("Continuing setup despite instance access issues", None, 2)
                return True
            return False
        
        if not is_running:
            start_instance = self.prompt("Would you like to start the instance?", "Y").lower() != 'n'
            if not start_instance:
                return False
            
            try:
                session = boto3.Session(profile_name=self.profile)
                ec2 = session.client('ec2')
                ec2.start_instances(InstanceIds=[instance_id])
                self.print_status("Instance start requested. This may take a few minutes...", None, 2)
                
                # Wait for instance to start
                for _ in range(30):  # 5 minute timeout
                    time.sleep(10)
                    ssm_accessible, is_running, is_complete = self.check_instance_setup(instance_id)
                    if is_running:
                        break
                
                if not is_running:
                    self.print_status("Timeout waiting for instance to start", False, 2)
                    return False
            except Exception as e:
                self.print_status(f"Error starting instance: {e}", False, 2)
                return False
        
        if is_complete:
            self.print_status("Instance setup is complete", True, 2)
            return True
        
        if not ssm_accessible:
            self.print_status("Waiting for SSM access...", None, 2)
            # Wait for SSM access
            for _ in range(30):  # 5 minute timeout
                time.sleep(10)
                ssm_accessible, is_running, is_complete = self.check_instance_setup(instance_id)
                if ssm_accessible or not is_running:
                    break
            
            if not ssm_accessible:
                self.print_status("Timeout waiting for SSM access", False, 2)
                continue_setup = self.prompt("Would you like to continue anyway?", "Y").lower() != 'n'
                if continue_setup:
                    self.print_status("Continuing setup despite SSM access issues", None, 2)
                    return True
                return False
        
        wait = self.prompt("Instance setup is not complete. Would you like to wait?", "Y").lower() != 'n'
        if not wait:
            self.print_status("Skipping instance setup check", None, 2)
            return True
        
        self.print_status("Waiting for setup to complete...", None, 2)
        dots = 0
        while True:
            ssm_accessible, is_running, is_complete = self.check_instance_setup(instance_id)
            
            if not is_running:
                self.print_status("Instance is no longer running", False, 2)
                continue_setup = self.prompt("Would you like to continue anyway?", "Y").lower() != 'n'
                if continue_setup:
                    self.print_status("Continuing setup despite instance issues", None, 2)
                    return True
                return False
            
            if not ssm_accessible:
                self.print_status("Lost SSM access to instance", False, 2)
                continue_setup = self.prompt("Would you like to continue anyway?", "Y").lower() != 'n'
                if continue_setup:
                    self.print_status("Continuing setup despite SSM access issues", None, 2)
                    return True
                return False
            
            if is_complete:
                self.print_status("Instance setup completed successfully", True, 2)
                return True
            
            dots = (dots + 1) % 4
            print(f"\r  {'.' * dots}{' ' * (3 - dots)}", end='', flush=True)
            time.sleep(10)
