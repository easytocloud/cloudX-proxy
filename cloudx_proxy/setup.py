import os
import time
import json
import subprocess
import platform
from pathlib import Path
from typing import Optional, Tuple
import boto3
from botocore.exceptions import ClientError
from ._1password import check_1password_cli, check_ssh_agent, list_ssh_keys, create_ssh_key, get_vaults, save_public_key

class CloudXSetup:
    def __init__(self, profile: str = "vscode", ssh_key: str = "vscode", ssh_config: str = None, 
                 aws_env: str = None, use_1password: bool = False):
        """Initialize cloudx-proxy setup.
        
        Args:
            profile: AWS profile name (default: "vscode")
            ssh_key: SSH key name (default: "vscode")
            ssh_config: SSH config file path (default: None, uses ~/.ssh/vscode/config)
            aws_env: AWS environment directory (default: None)
            use_1password: Use 1Password SSH agent for authentication (default: False)
        """
        self.profile = profile
        self.ssh_key = ssh_key
        self.aws_env = aws_env
        self.use_1password = use_1password
        self.home_dir = str(Path.home())
        self.onepassword_agent_sock = Path(self.home_dir) / ".1password" / "agent.sock"
        
        # Set up ssh config paths based on provided config or default
        if ssh_config:
            self.ssh_config_file = Path(os.path.expanduser(ssh_config))
            self.ssh_dir = self.ssh_config_file.parent
        else:
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

    def _set_directory_permissions(self, directory: Path) -> bool:
        """Set proper permissions (700) on a directory for Unix-like systems.
        
        Args:
            directory: Path to the directory
            
        Returns:
            bool: True if permissions were set successfully
        """
        try:
            if platform.system() != 'Windows':
                import stat
                directory.chmod(stat.S_IRWXU)  # 700 permissions (owner read/write/execute)
                self.print_status(f"Set {directory} permissions to 700", True, 2)
            return True
        except Exception as e:
            self.print_status(f"Error setting permissions: {str(e)}", False, 2)
            return False

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

    def _check_1password_availability(self) -> bool:
        """Check if 1Password CLI and SSH agent are available.
        
        Returns:
            bool: True if 1Password is available and configured
        """
        if not self.use_1password:
            return False
            
        self.print_status("Checking 1Password availability...")
        
        # Use our helper function to check 1Password CLI
        installed, authenticated, version = check_1password_cli()
        
        if not installed:
            self.print_status("1Password CLI not found. Please install it from https://1password.com/downloads/command-line/", False, 2)
            return False
        
        self.print_status(f"1Password CLI {version} installed", True, 2)
        
        if not authenticated:
            self.print_status("1Password CLI is not authenticated. Run 'op signin' first.", False, 2)
            return False
        
        self.print_status("1Password CLI is authenticated", True, 2)
        
        # Check if 1Password SSH agent is running
        agent_running = check_ssh_agent(str(self.onepassword_agent_sock))
        
        if not agent_running:
            self.print_status("1Password SSH agent is not running", False, 2)
            self.print_status("Please ensure 1Password SSH agent is enabled in 1Password settings", None, 2)
            return False
        
        self.print_status("1Password SSH agent is running", True, 2)
        return True

    def _create_1password_key(self) -> bool:
        """Create a new SSH key in 1Password.
        
        Returns:
            bool: True if successful
        """
        try:
            # Get vaults to determine where to store the key
            vaults = get_vaults()
            if not vaults:
                self.print_status("No 1Password vaults found", False, 2)
                return False
            
            # Display available vaults
            self.print_status("Creating a new SSH key in 1Password", None, 2)
            print("\n\033[96mAvailable 1Password vaults:\033[0m")
            for i, vault in enumerate(vaults):
                print(f"  {i+1}. {vault['name']}")
            
            # Let user select vault
            vault_num = self.prompt("Select vault number to store SSH key", "1")
            try:
                vault_idx = int(vault_num) - 1
                if vault_idx < 0 or vault_idx >= len(vaults):
                    self.print_status("Invalid vault number", False, 2)
                    return False
                selected_vault = vaults[vault_idx]['id']
            except ValueError:
                self.print_status("Invalid input", False, 2)
                return False
            
            # Create possible title variations for the 1Password item
            ssh_key_title_with_prefix = f"cloudX SSH Key - {self.ssh_key}"
            ssh_key_title_without_prefix = self.ssh_key
            
            # Check if a key with either title exists in 1Password
            ssh_keys = list_ssh_keys()
            
            # First check for our prefixed format, then for a plain key with the same name
            existing_key = next((key for key in ssh_keys if key['title'] == ssh_key_title_with_prefix), None)
            if not existing_key:
                existing_key = next((key for key in ssh_keys if key['title'] == ssh_key_title_without_prefix), None)
            
            if existing_key:
                key_title = existing_key['title']
                self.print_status(f"SSH key '{key_title}' already exists in 1Password", True, 2)
                # Get the public key
                result = subprocess.run(
                    ['op', 'item', 'get', existing_key['id'], '--fields', 'public key'],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if result.returncode == 0:
                    public_key = result.stdout.strip()
                    # Save it to the expected location
                    if save_public_key(public_key, f"{self.ssh_key_file}.pub"):
                        self.print_status(f"Saved existing public key to {self.ssh_key_file}.pub", True, 2)
                        return True
            else:
                # Create a new SSH key in 1Password
                self.print_status(f"Creating new SSH key '{ssh_key_title_with_prefix}' in 1Password...", None, 2)
                success, public_key, item_id = create_ssh_key(ssh_key_title_with_prefix, selected_vault)
                
                if not success:
                    self.print_status("Failed to create SSH key in 1Password", False, 2)
                    return False
                
                self.print_status("SSH key created successfully in 1Password", True, 2)
                
                # Save the public key to the expected location
                if save_public_key(public_key, f"{self.ssh_key_file}.pub"):
                    self.print_status(f"Saved public key to {self.ssh_key_file}.pub", True, 2)
                    return True
                else:
                    self.print_status(f"Failed to save public key to {self.ssh_key_file}.pub", False, 2)
                    return False
            
            # Remind user to enable the key in 1Password SSH agent
            self.print_status("\033[93mImportant: Make sure the key is enabled in 1Password's SSH agent settings\033[0m", None, 2)
            return True
            
        except Exception as e:
            self.print_status(f"Error creating key in 1Password: {str(e)}", False, 2)
            return False

    def setup_ssh_key(self) -> bool:
        """Set up SSH key pair.
        
        Returns:
            bool: True if key was set up successfully
        """
        self.print_header("SSH Key Configuration")
        
        # Check 1Password integration if requested
        if self.use_1password:
            op_available = self._check_1password_availability()
            if op_available:
                self.print_status("Using 1Password SSH agent for authentication", True, 2)
                
                # Always prefer to create keys in 1Password
                return self._create_1password_key()
            else:
                proceed = self.prompt("1Password integration not available. Continue with standard SSH key setup?", "Y").lower() != "n"
                if not proceed:
                    return False
                self.use_1password = False  # Fallback to standard setup
        
        self.print_status(f"Checking SSH key '{self.ssh_key}' configuration...")
        
        try:
            # Create .ssh/vscode directory if it doesn't exist
            self.ssh_dir.mkdir(parents=True, exist_ok=True)
            self.print_status("SSH directory exists", True, 2)
            
            # Set proper permissions on the vscode directory
            if not self._set_directory_permissions(self.ssh_dir):
                return False
            
            key_exists = self.ssh_key_file.exists() and (self.ssh_key_file.with_suffix('.pub')).exists()
            
            if key_exists:
                self.print_status(f"SSH key '{self.ssh_key}' exists", True, 2)
                # Set proper permissions on existing key files
                if platform.system() != 'Windows':
                    import stat
                    self.ssh_key_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions (owner read/write)
                    self.ssh_key_file.with_suffix('.pub').chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IROTH | stat.S_IRGRP)  # 644 permissions
                    self.print_status("Set key file permissions", True, 2)
            else:
                self.print_status(f"Generating new SSH key '{self.ssh_key}'...", None, 2)
                subprocess.run([
                    'ssh-keygen',
                    '-t', 'ed25519',
                    '-f', str(self.ssh_key_file),
                    '-N', ''  # Empty passphrase
                ], check=True)
                self.print_status("SSH key generated", True, 2)
                
                # Set proper permissions on newly generated key files
                if platform.system() != 'Windows':
                    import stat
                    self.ssh_key_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions (owner read/write)
                    self.ssh_key_file.with_suffix('.pub').chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IROTH | stat.S_IRGRP)  # 644 permissions
                    self.print_status("Set key file permissions", True, 2)
            
            # Standard key generation successful
            self.print_status("Key generated successfully", True, 2)
            return True

        except Exception as e:
            self.print_status(f"Error: {str(e)}", False, 2)
            continue_setup = self.prompt("Would you like to continue anyway?", "Y").lower() != 'n'
            if continue_setup:
                self.print_status("Continuing setup despite SSH key issues", None, 2)
                return True
            return False

    def _get_version(self) -> str:
        """Get the current version of the cloudx-proxy package.
        
        Returns:
            str: Version string
        """
        try:
            from . import __version__
            return __version__
        except (ImportError, AttributeError):
            return "unknown"
    
    def _build_proxy_command(self) -> str:
        """Build the ProxyCommand with appropriate parameters.
        
        Returns:
            str: The complete ProxyCommand string
        """
        proxy_command = "uvx cloudx-proxy connect %h %p"
        if self.profile != "vscode":
            proxy_command += f" --profile {self.profile}"
        if self.aws_env:
            proxy_command += f" --aws-env {self.aws_env}"
        if self.ssh_key != "vscode":
            proxy_command += f" --ssh-key {self.ssh_key}"
            
        return proxy_command
        
    def _build_auth_config(self) -> str:
        """Build the authentication configuration block.
        
        Returns:
            str: SSH config authentication section
        """
        if self.use_1password:
            # When using 1Password:
            # 1. Set IdentityAgent to the 1Password socket 
            # 2. Set IdentityFile to the PUBLIC key (.pub) to limit key search
            # 3. Set IdentitiesOnly to yes to avoid using ssh-agent keys
            return f"""    IdentityAgent {self.onepassword_agent_sock}
    IdentityFile {self.ssh_key_file}.pub
    IdentitiesOnly yes
"""
        else:
            # Standard SSH key configuration
            return f"""    IdentityFile {self.ssh_key_file}
    IdentitiesOnly yes
"""

    def _get_timestamp(self) -> str:
        """Get a formatted timestamp for configuration comments.
        
        Returns:
            str: Formatted timestamp
        """
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _build_generic_config(self) -> str:
        """Build a generic configuration block with common settings for all environments.
        
        Returns:
            str: Generic configuration block
        """
        version = self._get_version()
        timestamp = self._get_timestamp()
        
        # Start with metadata comment
        config = f"""
# Created by cloudx-proxy v{version} on {timestamp}
# Configuration type: generic
Host cloudx-*
    User ec2-user
    TCPKeepAlive yes
"""
        
        # Add SSH multiplexing configuration
        control_path = "~/.ssh/control/%r@%h:%p"
        if platform.system() == 'Windows':
            # Use forward slashes for Windows as well, SSH client will handle conversion
            control_path = "~/.ssh/control/%r@%h:%p"
            
        config += f"""    ControlMaster auto
    ControlPath {control_path}
    ControlPersist 4h
"""
        
        return config
        
    def _build_environment_config(self, cloudx_env: str) -> str:
        """Build an environment-specific configuration block.
        
        Args:
            cloudx_env: CloudX environment
            
        Returns:
            str: Environment configuration block
        """
        version = self._get_version()
        timestamp = self._get_timestamp()
        
        # Start with metadata comment
        config = f"""
# Created by cloudx-proxy v{version} on {timestamp}
# Configuration type: environment
Host cloudx-{cloudx_env}-*
"""
        # Add authentication configuration
        config += self._build_auth_config()
        
        # Add ProxyCommand
        config += f"""    ProxyCommand {self._build_proxy_command()}
"""
        
        return config
        
    def _build_host_config(self, cloudx_env: str, hostname: str, instance_id: str) -> str:
        """Build a host-specific configuration block.
        
        Args:
            cloudx_env: CloudX environment
            hostname: Hostname for the instance
            instance_id: EC2 instance ID
            
        Returns:
            str: Host configuration block
        """
        version = self._get_version()
        timestamp = self._get_timestamp()
        
        # Start with metadata comment
        config = f"""
# Created by cloudx-proxy v{version} on {timestamp}
# Configuration type: host
Host cloudx-{cloudx_env}-{hostname}
    HostName {instance_id}
"""
        
        return config
    
    def _check_config_exists(self, pattern: str, current_config: str) -> bool:
        """Check if a configuration pattern exists in the current config.
        
        Args:
            pattern: Host pattern to look for (e.g., 'cloudx-*', 'cloudx-dev-*')
            current_config: Current SSH config content
            
        Returns:
            bool: True if pattern exists in configuration
        """
        return f"Host {pattern}" in current_config
    
    def _extract_host_config(self, pattern: str, current_config: str) -> Tuple[str, str]:
        """Extract a host configuration block from the current config.
        
        Args:
            pattern: Host pattern to extract (e.g., 'cloudx-*', 'cloudx-dev-*')
            current_config: Current SSH config content
            
        Returns:
            Tuple[str, str]: Extracted host configuration, remaining configuration
        """
        lines = current_config.splitlines()
        host_config_lines = []
        remaining_lines = []
        in_host_block = False
        
        for line in lines:
            if line.strip() == f"Host {pattern}":
                in_host_block = True
                host_config_lines.append(line)
            elif in_host_block and line.strip().startswith("Host "):
                in_host_block = False
                remaining_lines.append(line)
            elif in_host_block:
                host_config_lines.append(line)
            else:
                remaining_lines.append(line)
                
        return "\n".join(host_config_lines), "\n".join(remaining_lines)
    
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
            # Check if host entry already exists
            host_pattern = f"cloudx-{cloudx_env}-{hostname}"
            if self._check_config_exists(host_pattern, current_config):
                # Extract existing host configuration
                host_config, remaining_config = self._extract_host_config(host_pattern, current_config)
                
                # Update host configuration
                host_config = self._build_host_config(cloudx_env, hostname, instance_id)
                
                # Write updated config
                with open(self.ssh_config_file, 'w') as f:
                    f.write(remaining_config)
                    f.write(host_config)
                
                self.print_status(f"Updated existing host entry for {host_pattern}", True, 2)
            else:
                # Generate new host entry
                host_entry = self._build_host_config(cloudx_env, hostname, instance_id)
                
                # Append host entry
                with open(self.ssh_config_file, 'a') as f:
                    f.write(host_entry)
                self.print_status(f"Added new host entry for {host_pattern}", True, 2)
            
            # Set proper permissions on the config file
            if platform.system() != 'Windows':
                import stat
                self.ssh_config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions (owner read/write)
                self.print_status("Set config file permissions to 600", True, 2)
                
            return True

        except Exception as e:
            self.print_status(f"\033[1;91mError:\033[0m {str(e)}", False, 2)
            continue_setup = self.prompt("Would you like to continue anyway?", "Y").lower() != 'n'
            if continue_setup:
                self.print_status("Continuing setup despite SSH config issues", None, 2)
                return True
            return False
    
    def _check_and_create_generic_config(self, current_config: str) -> Tuple[bool, str]:
        """Check if generic configuration exists and create it if needed.
        
        Args:
            current_config: Current SSH config content
            
        Returns:
            Tuple[bool, str]: Success flag, Updated configuration
        """
        if self._check_config_exists("cloudx-*", current_config):
            self.print_status("Found existing generic config for cloudx-*", True, 2)
            return True, current_config
        
        self.print_status("Creating generic config for cloudx-*", None, 2)
        generic_config = self._build_generic_config()
        
        # Append generic config to current config
        updated_config = current_config
        if updated_config and not updated_config.endswith('\n'):
            updated_config += '\n'
        updated_config += generic_config
        
        return True, updated_config
        
    def _check_and_create_environment_config(self, cloudx_env: str, current_config: str) -> Tuple[bool, str]:
        """Check if environment configuration exists and create it if needed.
        
        Args:
            cloudx_env: CloudX environment
            current_config: Current SSH config content
            
        Returns:
            Tuple[bool, str]: Success flag, Updated configuration
        """
        if self._check_config_exists(f"cloudx-{cloudx_env}-*", current_config):
            self.print_status(f"Found existing config for cloudx-{cloudx_env}-*", True, 2)
            
            # Option to override if needed
            choice = self.prompt(
                "Would you like to \n"
                "  1: override the existing environment config\n"
                "  2: keep existing environment config?\n"
                "Select an option",
                "2"
            )
            
            if choice == "1":
                # Remove existing config for this environment
                self.print_status("Removing existing environment configuration", None, 2)
                env_config, remaining_config = self._extract_host_config(f"cloudx-{cloudx_env}-*", current_config)
                
                # Create new environment config
                env_config = self._build_environment_config(cloudx_env)
                
                # Append new environment config to remaining config
                updated_config = remaining_config
                if updated_config and not updated_config.endswith('\n'):
                    updated_config += '\n'
                updated_config += env_config
                
                return True, updated_config
            
            return True, current_config
        
        self.print_status(f"Creating environment config for cloudx-{cloudx_env}-*", None, 2)
        env_config = self._build_environment_config(cloudx_env)
        
        # Append environment config to current config
        updated_config = current_config
        if updated_config and not updated_config.endswith('\n'):
            updated_config += '\n'
        updated_config += env_config
        
        return True, updated_config

    def _ensure_control_dir(self) -> bool:
        """Create SSH control directory with proper permissions.
        
        Creates ~/.ssh/control directory with 700 permissions on Unix-like systems,
        or appropriate permissions on Windows.
        
        Returns:
            bool: True if directory was created or exists with proper permissions
        """
        try:
            # Create control directory path
            control_dir = Path(self.home_dir) / ".ssh" / "control"
            
            # Create directory if it doesn't exist
            if not control_dir.exists():
                control_dir.mkdir(parents=True, exist_ok=True)
                self.print_status(f"Created control directory: {control_dir}", True, 2)
            
            # Set proper permissions
            return self._set_directory_permissions(control_dir)
            
        except Exception as e:
            self.print_status(f"Error creating control directory: {str(e)}", False, 2)
            return False
    
    def setup_ssh_config(self, cloudx_env: str, instance_id: str, hostname: str) -> bool:
        """Set up SSH config for the instance using a three-tier configuration approach.
        
        This method implements a hierarchical SSH configuration with three levels:
        1. Generic (cloudx-*): Common settings for all environments
           - User settings
           - TCP keepalive
           - SSH multiplexing configuration
        
        2. Environment (cloudx-{env}-*): Environment-specific settings
           - Authentication configuration (identity settings)
           - ProxyCommand with environment-specific parameters
        
        3. Host (cloudx-{env}-hostname): Instance-specific settings
           - HostName (instance ID)
           - Optional overrides for incompatible settings
        
        Args:
            cloudx_env: CloudX environment (e.g., dev, prod)
            instance_id: EC2 instance ID
            hostname: Hostname for the instance
        
        Returns:
            bool: True if config was set up successfully
        """
        self.print_header("SSH Configuration")
        self.print_status("Setting up SSH configuration with three-tier approach...")
        
        try:
            # Ensure control directory exists with proper permissions
            if not self._ensure_control_dir():
                return False
            
            # Initialize or read current configuration
            current_config = ""
            if self.ssh_config_file.exists():
                current_config = self.ssh_config_file.read_text()
            
            # 1. Check and create generic config (highest level)
            self.print_status("Checking generic configuration...", None, 2)
            success, current_config = self._check_and_create_generic_config(current_config)
            if not success:
                return False
            
            # 2. Check and create environment config
            self.print_status("Checking environment configuration...", None, 2)
            success, current_config = self._check_and_create_environment_config(cloudx_env, current_config)
            if not success:
                return False
                
            # Write the updated config with generic and environment tiers
            self.ssh_config_file.parent.mkdir(parents=True, exist_ok=True)
            self.ssh_config_file.write_text(current_config)
            self.print_status("Generic and environment configurations created", True, 2)
            
            # Set proper permissions on the config file
            if platform.system() != 'Windows':
                import stat
                self.ssh_config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions
                self.print_status("Set config file permissions to 600", True, 2)
            
            # 3. Add or update host entry (lowest level)
            self.print_status(f"Adding/updating host entry for cloudx-{cloudx_env}-{hostname}", None, 2)
            if not self._add_host_entry(cloudx_env, instance_id, hostname, current_config):
                return False
            
            # Handle system SSH config integration
            system_config_path = Path(self.home_dir) / ".ssh" / "config"
            
            # Ensure ~/.ssh directory has proper permissions
            ssh_parent_dir = Path(self.home_dir) / ".ssh"
            if not ssh_parent_dir.exists():
                ssh_parent_dir.mkdir(parents=True, exist_ok=True)
                self.print_status(f"Created SSH directory: {ssh_parent_dir}", True, 2)
            self._set_directory_permissions(ssh_parent_dir)
            
            # Handle system config integration
            same_file = False
            if self.ssh_config_file.exists() and system_config_path.exists():
                try:
                    same_file = self.ssh_config_file.samefile(system_config_path)
                except:
                    same_file = str(self.ssh_config_file) == str(system_config_path)
            else:
                same_file = str(self.ssh_config_file) == str(system_config_path)
                
            if same_file:
                self.print_status("Using system SSH config directly, no Include needed", True, 2)
            else:
                # Otherwise, make sure the system config includes our config file
                include_line = f"Include {self.ssh_config_file}\n"
                
                if system_config_path.exists():
                    content = system_config_path.read_text()
                    if include_line not in content:
                        with open(system_config_path, 'a') as f:
                            f.write(f"\n{include_line}")
                        self.print_status("Added include line to system SSH config", True, 2)
                    else:
                        self.print_status("System SSH config already includes our config", True, 2)
                    
                    # Set correct permissions on system config file
                    if platform.system() != 'Windows':
                        import stat
                        system_config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions
                        self.print_status("Set system config file permissions to 600", True, 2)
                else:
                    system_config_path.write_text(include_line)
                    self.print_status("Created system SSH config with include line", True, 2)
                    
                    # Set correct permissions on newly created system config file
                    if platform.system() != 'Windows':
                        import stat
                        system_config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions
                        self.print_status("Set system config file permissions to 600", True, 2)

            self.print_status("SSH configuration summary:", None)
            self.print_status(f"System config: {system_config_path}", None, 2)
            self.print_status(f"cloudx-proxy config: {self.ssh_config_file}", None, 2)
            self.print_status(f"SSH key directory: {self.ssh_dir}", None, 2)
            self.print_status(f"Connect using: ssh cloudx-{cloudx_env}-{hostname}", None, 2)
            
            return True

        except Exception as e:
            self.print_status(f"\033[1;91mError:\033[0m {str(e)}", False, 2)
            continue_setup = self.prompt("Would you like to continue anyway?", "Y").lower() != 'n'
            if continue_setup:
                self.print_status("Continuing setup despite SSH config issues", None, 2)
                return True
            return False

    def check_instance_setup(self, instance_id: str, hostname: str, cloudx_env: str) -> bool:
        """Check if instance is accessible via SSH.
        
        Args:
            instance_id: EC2 instance ID
            hostname: Hostname for the instance
            cloudx_env: CloudX environment
        
        Returns:
            bool: True if instance is accessible
        """
        ssh_host = f"cloudx-{cloudx_env}-{hostname}"
        self.print_status(f"Checking SSH connection to {ssh_host}...", None, 4)
        
        try:
            # Try to connect with a simple command that will exit immediately
            result = subprocess.run(
                ['ssh', ssh_host, 'exit'],
                capture_output=True,
                text=True,
                timeout=10  # 10 second timeout
            )
            
            if result.returncode == 0:
                self.print_status("SSH connection successful", True, 4)
                return True
            else:
                self.print_status("SSH connection failed", False, 4)
                if "Connection refused" in result.stderr:
                    self.print_status("Instance appears to be starting up. Please try again in a few minutes.", None, 4)
                elif "Connection timed out" in result.stderr:
                    self.print_status("Instance may be stopped. Please start it through the appropriate channels.", None, 4)
                else:
                    self.print_status(f"Error: {result.stderr.strip()}", None, 4)
                return False
                
        except subprocess.TimeoutExpired:
            self.print_status("SSH connection timed out", False, 4)
            self.print_status("Instance may be stopped or still starting up", None, 4)
            return False
        except Exception as e:
            self.print_status(f"Error checking SSH connection: {str(e)}", False, 4)
            return False

    def wait_for_setup_completion(self, instance_id: str, hostname: str, cloudx_env: str) -> bool:
        """Wait for instance to become accessible via SSH.
        
        Args:
            instance_id: EC2 instance ID
            hostname: Hostname for the instance
            cloudx_env: CloudX environment
        
        Returns:
            bool: True if instance is accessible or user chose to continue
        """
        self.print_header("Instance Access Check")
        
        if self.check_instance_setup(instance_id, hostname, cloudx_env):
            return True
            
        wait = self.prompt("Would you like to wait for the instance to become accessible?", "Y").lower() != 'n'
        if not wait:
            return False
        
        self.print_status("Waiting for SSH access...", None, 2)
        dots = 0
        attempts = 0
        max_attempts = 30  # 5 minute timeout (10 seconds * 30)
        
        while attempts < max_attempts:
            if self.check_instance_setup(instance_id, hostname, cloudx_env):
                return True
            
            dots = (dots + 1) % 4
            print(f"\r  {'.' * dots}{' ' * (3 - dots)}", end='', flush=True)
            time.sleep(10)
            attempts += 1
        
        self.print_status("Timeout waiting for SSH access", False, 2)
        continue_setup = self.prompt("Would you like to continue anyway?", "Y").lower() != 'n'
        if continue_setup:
            self.print_status("Continuing setup despite SSH access issues", None, 2)
            return True
        return False
