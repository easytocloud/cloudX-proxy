import os
import time
import json
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import boto3
from botocore.exceptions import ClientError

class CloudXSetup:
    def __init__(self, profile: str = "vscode", ssh_key: str = "vscode", aws_env: str = None):
        """Initialize CloudX setup.
        
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
        self.using_1password = False

    def setup_aws_profile(self) -> bool:
        """Set up AWS profile using aws configure command.
        
        Returns:
            bool: True if profile was set up successfully
        """
        try:
            # Configure AWS environment if specified
            if self.aws_env:
                aws_env_dir = os.path.expanduser(f"~/.aws/aws-envs/{self.aws_env}")
                os.environ["AWS_CONFIG_FILE"] = os.path.join(aws_env_dir, "config")
                os.environ["AWS_SHARED_CREDENTIALS_FILE"] = os.path.join(aws_env_dir, "credentials")

            # Check if profile exists
            session = boto3.Session(profile_name=self.profile)
            try:
                session.client('sts').get_caller_identity()
                print(f"AWS profile '{self.profile}' already exists and is valid.")
                return True
            except ClientError:
                pass

            # Profile doesn't exist or is invalid, set it up
            print(f"Setting up AWS profile '{self.profile}'...")
            print("Please enter your AWS credentials:")
            
            # Use aws configure command
            subprocess.run([
                'aws', 'configure',
                '--profile', self.profile
            ], check=True)

            # Verify the profile works
            session = boto3.Session(profile_name=self.profile)
            identity = session.client('sts').get_caller_identity()
            user_arn = identity['Arn']
            
            if not any(part.startswith('cloudX-') for part in user_arn.split('/')):
                print(f"Warning: User ARN '{user_arn}' does not match expected format cloudX-{{env}}-{{user}}")
            
            return True

        except Exception as e:
            print(f"Error setting up AWS profile: {e}")
            return False

    def setup_ssh_key(self) -> bool:
        """Set up SSH key pair.
        
        Returns:
            bool: True if key was set up successfully
        """
        try:
            # Create .ssh/vscode directory if it doesn't exist
            self.ssh_dir.mkdir(parents=True, exist_ok=True)
            
            key_exists = self.ssh_key_file.exists() and (self.ssh_key_file.with_suffix('.pub')).exists()
            
            if key_exists:
                print(f"SSH key '{self.ssh_key}' already exists.")
                self.using_1password = input("Would you like to use 1Password SSH agent? (y/N): ").lower() == 'y'
                if not self.using_1password:
                    store_in_1password = input("Would you like to store the private key in 1Password? (y/N): ").lower() == 'y'
                    if store_in_1password:
                        self._store_key_in_1password()
            else:
                print(f"Generating new SSH key '{self.ssh_key}'...")
                subprocess.run([
                    'ssh-keygen',
                    '-t', 'ed25519',
                    '-f', str(self.ssh_key_file),
                    '-N', ''  # Empty passphrase
                ], check=True)
                
                self.using_1password = input("Would you like to use 1Password SSH agent? (y/N): ").lower() == 'y'
                if not self.using_1password:
                    store_in_1password = input("Would you like to store the private key in 1Password? (y/N): ").lower() == 'y'
                    if store_in_1password:
                        self._store_key_in_1password()
            
            return True

        except Exception as e:
            print(f"Error setting up SSH key: {e}")
            return False

    def _store_key_in_1password(self) -> bool:
        """Store SSH private key in 1Password.
        
        Returns:
            bool: True if key was stored successfully
        """
        try:
            subprocess.run(['op', '--version'], check=True, capture_output=True)
            print("Storing private key in 1Password...")
            subprocess.run([
                'op', 'document', 'create',
                str(self.ssh_key_file),
                '--title', f'CloudX SSH Key - {self.ssh_key}'
            ], check=True)
            return True
        except subprocess.CalledProcessError:
            print("Error: 1Password CLI not installed or not signed in.")
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
        try:
            # Check if we need to create base config
            need_base_config = True
            if self.ssh_config_file.exists():
                current_config = self.ssh_config_file.read_text()
                # Check if configuration for this environment already exists
                if f"Host cloudx-{cloudx_env}-*" in current_config:
                    need_base_config = False
            
            if need_base_config:
                # Build ProxyCommand with all necessary parameters
                proxy_command = f"uvx cloudx-proxy connect %h %p --profile {self.profile}"
                if self.aws_env:
                    proxy_command += f" --aws-env {self.aws_env}"
                if self.ssh_key != "vscode":
                    proxy_command += f" --key-path {self.ssh_key_file}.pub"

                # Build base configuration
                base_config = f"""# CloudX SSH Configuration
Host cloudx-{cloudx_env}-*
    User ec2-user
"""
                # Add 1Password or standard key configuration
                if self.using_1password:
                    base_config += f"""    IdentityAgent ~/.1password/agent.sock
    IdentityFile {self.ssh_key_file}.pub
    IdentitiesOnly yes
"""
                else:
                    base_config += f"""    IdentityFile {self.ssh_key_file}
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

            # Add specific host entry
            host_entry = f"""
Host cloudx-{cloudx_env}-{hostname}
    HostName {instance_id}
"""
            with open(self.ssh_config_file, 'a') as f:
                f.write(host_entry)

            # Ensure main SSH config includes our config
            main_config = Path(self.home_dir) / ".ssh" / "config"
            include_line = f"Include {self.ssh_config_file}\n"
            
            if main_config.exists():
                content = main_config.read_text()
                if include_line not in content:
                    with open(main_config, 'a') as f:
                        f.write(f"\n{include_line}")
            else:
                main_config.write_text(include_line)

            print(f"\nSSH configuration has been set up:")
            print(f"- Main config file: {main_config}")
            print(f"- CloudX config file: {self.ssh_config_file}")
            print(f"\nYou can now connect using: ssh cloudx-{cloudx_env}-{hostname}")
            
            return True

        except Exception as e:
            print(f"Error setting up SSH config: {e}")
            return False

    def check_instance_setup(self, instance_id: str) -> Tuple[bool, bool]:
        """Check if instance setup is complete.
        
        Args:
            instance_id: EC2 instance ID
        
        Returns:
            Tuple[bool, bool]: (is_running, is_setup_complete)
        """
        try:
            session = boto3.Session(profile_name=self.profile)
            ssm = session.client('ssm')
            
            # Check if instance is online in SSM
            response = ssm.describe_instance_information(
                Filters=[{'Key': 'InstanceIds', 'Values': [instance_id]}]
            )
            is_running = bool(response['InstanceInformationList'])
            
            if not is_running:
                return False, False
            
            # Check setup status using SSM command
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
            
            return True, is_setup_complete

        except Exception as e:
            print(f"Error checking instance setup: {e}")
            return False, False

    def wait_for_setup_completion(self, instance_id: str) -> bool:
        """Wait for instance setup to complete.
        
        Args:
            instance_id: EC2 instance ID
        
        Returns:
            bool: True if setup completed successfully
        """
        print(f"Checking setup status for instance {instance_id}...")
        
        is_running, is_complete = self.check_instance_setup(instance_id)
        
        if not is_running:
            print("Error: Instance is not running or not accessible via SSM")
            return False
        
        if is_complete:
            print("Instance setup is already complete")
            return True
        
        wait = input("Instance setup is not complete. Would you like to wait? (Y/n): ").lower() != 'n'
        if not wait:
            return False
        
        print("Waiting for setup to complete", end='', flush=True)
        while True:
            is_running, is_complete = self.check_instance_setup(instance_id)
            
            if not is_running:
                print("\nError: Instance is no longer running or accessible")
                return False
            
            if is_complete:
                print("\nInstance setup completed successfully")
                return True
            
            print(".", end='', flush=True)
            time.sleep(10)
