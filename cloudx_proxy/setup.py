import os
import re
import time
import json
import subprocess
import platform
from pathlib import Path
from typing import Optional, Tuple
import boto3
from botocore.exceptions import ClientError
from ._1password import check_1password_cli, check_ssh_agent, list_ssh_keys, create_ssh_key, get_vaults, save_public_key
from .colors import header, success, error, warning, info, prompt as color_prompt, status_symbol, format_path, format_command

class CloudXSetup:
    # Define SSH key prefix as a constant
    SSH_KEY_PREFIX = "cloudX SSH Key - "

    @staticmethod
    def validate_instance_id(instance_id: str) -> bool:
        """Validate EC2 instance ID format.

        EC2 instance IDs must:
        - Start with 'i-'
        - Be followed by 8 or 17 hexadecimal characters

        Args:
            instance_id: The instance ID to validate

        Returns:
            bool: True if valid, False otherwise
        """
        if not instance_id:
            return False

        # Match i- followed by exactly 8 or 17 hexadecimal characters
        pattern = r'^i-[0-9a-f]{8}$|^i-[0-9a-f]{17}$'
        return bool(re.match(pattern, instance_id, re.IGNORECASE))

    def get_instance_tags(self, instance_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Fetch instance tags and extract environment and hostname.

        Queries EC2 for the instance tags and extracts:
        - Environment from the 'Environment' tag
        - Hostname from the 'Name' tag (expects format: cloudX-{env}-{hostname} | {username})

        Args:
            instance_id: The EC2 instance ID

        Returns:
            Tuple[Optional[str], Optional[str]]: (environment, hostname) or (None, None) on failure
        """
        try:
            # Configure AWS environment if specified
            if self.aws_env:
                aws_env_dir = os.path.expanduser(f"~/.aws/aws-envs/{self.aws_env}")
                os.environ["AWS_CONFIG_FILE"] = os.path.join(aws_env_dir, "config")
                os.environ["AWS_SHARED_CREDENTIALS_FILE"] = os.path.join(aws_env_dir, "credentials")

            session = boto3.Session(profile_name=self.profile)
            ec2 = session.client('ec2')

            response = ec2.describe_instances(InstanceIds=[instance_id])

            if not response['Reservations'] or not response['Reservations'][0]['Instances']:
                self.print_status(f"Instance {instance_id} not found", False, 2)
                return None, None

            instance = response['Reservations'][0]['Instances'][0]
            tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}

            # Extract Environment tag
            environment = tags.get('Environment')
            if environment:
                self.print_status(f"Found Environment tag: {environment}", True, 2)

            # Extract hostname from Name tag
            # Format: cloudX-{env}-{hostname} | {username}
            # We only need the first part before ' | '
            hostname = None
            name_tag = tags.get('Name', '')
            if name_tag:
                # Get the first part (before ' | ' if present)
                ssh_hostname = name_tag.split(' | ')[0].strip()

                # Parse cloudX-{env}-{hostname} or cloudx-{env}-{hostname}
                match = re.match(r'^cloud[xX]-([^-]+)-(.+)$', ssh_hostname)
                if match:
                    hostname = match.group(2)
                    self.print_status(f"Found hostname from Name tag: {hostname}", True, 2)
                else:
                    self.print_status(f"Name tag '{name_tag}' does not match cloudX-{{env}}-{{hostname}} format", None, 2)

            return environment, hostname

        except ClientError as e:
            self.print_status(f"Error fetching instance tags: {e.response['Error']['Message']}", False, 2)
            return None, None
        except Exception as e:
            self.print_status(f"Error fetching instance tags: {str(e)}", False, 2)
            return None, None
    
    def __init__(self, profile: str = "cloudX", ssh_key: str = "cloudX", ssh_config: str = None,
                 ssh_dir: str = None, aws_env: str = None, use_1password: str = None, instance_id: str = None,
                 ssh_host_prefix: str = "cloudx", non_interactive: bool = False, dry_run: bool = False):
        """Initialize cloudx-proxy setup.
        
        Args:
            profile: AWS profile name (default: "cloudX")
            ssh_key: SSH key name (default: "cloudX")
            ssh_config: SSH config file path (default: None)
            ssh_dir: Directory for SSH keys and config (default: None)
            aws_env: AWS environment directory (default: None)
            use_1password: Use 1Password SSH agent for authentication. Can be True/False or a vault name (default: None)
            instance_id: EC2 instance ID to set up connection for (optional)
            ssh_host_prefix: Prefix for SSH hosts (default: "cloudx")
            non_interactive: Non-interactive mode, use defaults for all prompts (default: False)
            dry_run: Preview mode, show what would be done without executing (default: False)
        """
        self.profile = profile
        self.ssh_key = ssh_key
        self.aws_env = aws_env
        self.ssh_host_prefix = ssh_host_prefix
        
        # Handle 1Password integration
        if use_1password is None:
            self.use_1password = False
            self.op_vault = None
        elif isinstance(use_1password, bool) or use_1password.lower() == 'true':
            self.use_1password = True
            self.op_vault = "Private"  # Default vault
        else:
            self.use_1password = True
            self.op_vault = use_1password
        self.instance_id = instance_id
        self.non_interactive = non_interactive
        self.dry_run = dry_run
        self.home_dir = str(Path.home())
        self.onepassword_agent_sock = Path(self.home_dir) / ".1password" / "agent.sock"
        self.onepassword_agent_sock_macos = Path(self.home_dir) / "Library" / "Group Containers" / "2BUA8C4S2C.com.1password" / "t" / "agent.sock"
        
        self.pending_migration = False
        
        # Set up ssh config paths based on provided config or default
        if ssh_dir:
            self.ssh_dir = Path(os.path.expanduser(ssh_dir))
            self.ssh_config_file = self.ssh_dir / "config"
        elif ssh_config:
            self.ssh_config_file = Path(os.path.expanduser(ssh_config))
            self.ssh_dir = self.ssh_config_file.parent
        else:
            # Default logic: check for vscode, but default to cloudX
            cloudx_dir = Path(self.home_dir) / ".ssh" / "cloudX"
            vscode_dir = Path(self.home_dir) / ".ssh" / "vscode"
            
            if vscode_dir.exists() and not cloudx_dir.exists():
                # Existing vscode setup found, mark for potential migration
                self.ssh_dir = vscode_dir
                self.pending_migration = True
            else:
                # Default to cloudX
                self.ssh_dir = cloudx_dir
                
            self.ssh_config_file = self.ssh_dir / "config"
        
        self.ssh_key_file = self.ssh_dir / f"{ssh_key}"
        self.default_env = None

    def _ensure_onepassword_agent_symlink(self) -> bool:
        """Ensure ~/.1password/agent.sock points to the macOS agent location."""
        if platform.system() != 'Darwin':
            return False

        if not self.onepassword_agent_sock_macos.exists():
            self.print_status(
                "macOS default 1Password agent socket not found at ~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock",
                False,
                2,
            )
            return False

        try:
            self.onepassword_agent_sock.parent.mkdir(parents=True, exist_ok=True)

            if self.onepassword_agent_sock.exists() or self.onepassword_agent_sock.is_symlink():
                try:
                    current_target = self.onepassword_agent_sock.resolve(strict=False)
                except FileNotFoundError:
                    current_target = None

                if self.onepassword_agent_sock.is_symlink() and current_target == self.onepassword_agent_sock_macos:
                    self.print_status("1Password agent symlink already points to default location", True, 2)
                    return True

                self.print_status("Replacing existing 1Password agent socket entry", None, 2)
                self.onepassword_agent_sock.unlink(missing_ok=True)

            self.onepassword_agent_sock.symlink_to(self.onepassword_agent_sock_macos)
            self.print_status("Created symlink to 1Password agent socket", True, 2)
            return True
        except Exception as e:
            self.print_status(f"Failed to create symlink: {str(e)}", False, 2)
            return False

    def print_header(self, text: str) -> None:
        """Print a section header.

        Args:
            text: The header text
        """
        print(f"\n\n{header(f'=== {text} ===')}")

    def print_status(self, message: str, status: bool = None, indent: int = 0) -> None:
        """Print a status message with optional checkmark/cross.

        Args:
            message: The message to print
            status: True for success (✓), False for failure (✗), None for no symbol
            indent: Number of spaces to indent
        """
        prefix = " " * indent
        print(f"{prefix}{status_symbol(status)} {message}")

    def prompt(self, message: str, default: str = None) -> str:
        """Display a colored prompt for user input.
        
        Args:
            message: The prompt message
            default: Default value (shown in brackets)
        
        Returns:
            str: User's input or default value
        """
        # In non-interactive mode, always use the default value
        if self.non_interactive:
            if default:
                self.print_status(f"{message}: Using default [{default}]", None, 2)
                return default
            else:
                self.print_status(f"{message}: No default value available", False, 2)
                raise ValueError(f"Non-interactive mode requires default value for: {message}")
        
        # Interactive prompt
        if default:
            prompt_text = f"{color_prompt(message)} [{default}]: "
        else:
            prompt_text = f"{color_prompt(message)}: "
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
        if self.dry_run:
            self.print_status(f"[DRY RUN] Would check AWS profile configuration for '{self.profile}'")
            if self.aws_env:
                self.print_status(f"[DRY RUN] Would configure AWS environment: {self.aws_env}", None, 2)
            self.print_status(f"[DRY RUN] Would verify AWS credentials and extract cloudX environment", None, 2)
            return True
            
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
                print(info("Please enter your AWS credentials:"))
                
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
                identity_arn = identity['Arn']

                # Determine if the identity refers to an IAM user or an assumed role/SSO session
                resource = identity_arn.split(':', 5)[5]  # arn:partition:service:region:account:resource
                resource_type, _, resource_details = resource.partition('/')

                if resource_type == 'user' and resource_details:
                    path_segments = [segment for segment in resource_details.split('/') if segment]
                    cloudx_segment = next(
                        (segment for segment in reversed(path_segments) if segment.startswith('cloudX-')),
                        None,
                    )

                    if cloudx_segment:
                        # Extract env from cloudX-{env}-{user} or cloudx-{env}-{user}
                        parts = cloudx_segment.split('-')
                        if len(parts) >= 3:
                            self.default_env = parts[1]
                        self.print_status(f"AWS profile '{self.profile}' exists and matches cloudX format", True, 2)
                        return True
                    
                    # Also check for lowercase cloudx- prefix
                    cloudx_lower_segment = next(
                        (segment for segment in reversed(path_segments) if segment.startswith('cloudx-')),
                        None,
                    )
                    
                    if cloudx_lower_segment:
                        # Extract env from cloudx-{env}-{user}
                        parts = cloudx_lower_segment.split('-')
                        if len(parts) >= 3:
                            self.default_env = parts[1]
                        self.print_status(f"AWS profile '{self.profile}' exists and matches cloudx format", True, 2)
                        return True

                    self.print_status(
                        "AWS profile exists but doesn't match cloudX-{env}-{user} format", False, 2
                    )
                    self.print_status("Please ensure your IAM user follows the format: cloudX-{env}-{username}", None, 2)
                    return False

                # Non-user identities (roles, SSO, etc.) should skip the cloudX naming check
                self.print_status(
                    "AWS profile uses IAM role/SSO credentials; skipping cloudX user format check", True, 2
                )
                return True
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
        
        # Check if 1Password SSH agent socket exists at ~/.1password/agent.sock
        if not self.onepassword_agent_sock.exists():
            self.print_status("1Password SSH agent socket not found at ~/.1password/agent.sock", False, 2)

            if not self._ensure_onepassword_agent_symlink():
                self.print_status("1Password SSH agent is not available", False, 2)
                self.print_status("Please ensure 1Password SSH agent is enabled in 1Password settings", None, 2)
                self.print_status("1Password integration is not supported in this configuration", False, 2)
                return False
        elif platform.system() == 'Darwin' and self.onepassword_agent_sock.is_symlink():
            try:
                current_target = self.onepassword_agent_sock.resolve(strict=False)
            except FileNotFoundError:
                current_target = None

            if current_target != self.onepassword_agent_sock_macos and self.onepassword_agent_sock_macos.exists():
                self.print_status("Updating 1Password agent symlink to default location", None, 2)
                if not self._ensure_onepassword_agent_symlink():
                    self.print_status("1Password integration is not supported in this configuration", False, 2)
                    return False
        
        self.print_status("1Password SSH agent socket is available", True, 2)
        
        # If using a vault other than "Private", warn the user
        if self.op_vault and self.op_vault != "Private":
            self.print_status(warning(f"Warning: Using vault '{self.op_vault}' instead of default 'Private' vault"), None, 2)
            self.print_status(warning("Make sure to enable this vault for SSH in 1Password settings"), None, 2)
            self.print_status(warning("By default, only the 'Private' vault is enabled for SSH"), None, 2)
        
        return True

    def _create_1password_key(self) -> bool:
        """Create a new SSH key in 1Password.
        
        Returns:
            bool: True if successful
        """
        try:
            # Create possible title variations for the 1Password item
            ssh_key_title_with_prefix = f"{self.SSH_KEY_PREFIX}{self.ssh_key}"
            ssh_key_title_without_prefix = self.ssh_key
            
            # First check if key exists in any vault
            ssh_keys = list_ssh_keys()
            
            # Check for both prefixed and non-prefixed format
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
                        self.print_status(f"Failed to save public key to {self.ssh_key_file}.pub", False, 2)
                        return False
                else:
                    self.print_status(f"Failed to retrieve public key from 1Password", False, 2)
                    return False
            
            # If we reach here, the key doesn't exist and we need to create it
            # Get vaults to determine where to store the key
            vaults = get_vaults()
            if not vaults:
                self.print_status("No 1Password vaults found", False, 2)
                return False
            
            # Use the specified vault or prompt the user to select one
            if self.op_vault:
                # Find the vault by name
                selected_vault = None
                for vault in vaults:
                    if vault['name'].lower() == self.op_vault.lower():
                        selected_vault = vault['id']
                        self.print_status(f"Using specified 1Password vault: {self.op_vault}", True, 2)
                        break
                
                # If the specified vault wasn't found, warn the user and prompt for selection
                if not selected_vault:
                    self.print_status(f"Specified vault '{self.op_vault}' not found", False, 2)
                    
                    # Display available vaults
                    self.print_status("Available 1Password vaults:", None, 2)
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
            else:
                # No vault specified, prompt the user
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
            self.print_status(warning("Important: Make sure the key is enabled in 1Password's SSH agent settings"), None, 2)
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
        
        if self.dry_run:
            self.print_status(f"[DRY RUN] Would check SSH key '{self.ssh_key}' configuration")
            if self.use_1password:
                self.print_status(f"[DRY RUN] Would use 1Password SSH agent for authentication", None, 2)
                self.print_status(f"[DRY RUN] Would create or find SSH key in vault: {self.op_vault}", None, 2)
            else:
                self.print_status(f"[DRY RUN] Would create SSH key pair at: {self.ssh_key_file}", None, 2)
                self.print_status(f"[DRY RUN] Would set proper file permissions", None, 2)
            return True
        
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
            # Create SSH directory if it doesn't exist
            self.ssh_dir.mkdir(parents=True, exist_ok=True)
            self.print_status("SSH directory exists", True, 2)
            
            # Set proper permissions on the SSH directory
            if not self._set_directory_permissions(self.ssh_dir):
                return False
            
            pub_key_file = self.ssh_key_file.with_suffix('.pub')
            private_key_exists = self.ssh_key_file.exists()
            pub_key_exists = pub_key_file.exists()
            
            # Check if only public key exists (private key likely in 1Password)
            if pub_key_exists and not private_key_exists:
                self.print_status(f"Public key '{self.ssh_key}.pub' found (private key in 1Password or secure storage)", True, 2)
                self.print_status("Using existing key configuration", True, 2)
                return True
            
            key_exists = private_key_exists and pub_key_exists
            
            if key_exists:
                self.print_status(f"SSH key pair '{self.ssh_key}' already exists", True, 2)
                # Set proper permissions on existing key files
                if platform.system() != 'Windows':
                    import stat
                    self.ssh_key_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions (owner read/write)
                    pub_key_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IROTH | stat.S_IRGRP)  # 644 permissions
                    self.print_status("Updated key file permissions", True, 2)
                self.print_status("Using existing SSH key", True, 2)
            else:
                self.print_status(f"Generating new SSH key '{self.ssh_key}'...", None, 2)
                subprocess.run([
                    'ssh-keygen',
                    '-t', 'ed25519',
                    '-f', str(self.ssh_key_file),
                    '-N', ''  # Empty passphrase
                ], check=True)
                self.print_status("SSH key generated successfully", True, 2)
                
                # Set proper permissions on newly generated key files
                if platform.system() != 'Windows':
                    import stat
                    self.ssh_key_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions (owner read/write)
                    pub_key_file.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IROTH | stat.S_IRGRP)  # 644 permissions
                    self.print_status("Set key file permissions", True, 2)
            
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
        
        # Always include profile and ssh-key to ensure connect has all information
        proxy_command += f" --profile {self.profile}"
        
        if self.aws_env:
            proxy_command += f" --aws-env {self.aws_env}"
            
        proxy_command += f" --ssh-key {self.ssh_key}"
        
        # Always include ssh-dir or ssh-config
        # If the config file is standard (ssh_dir/config), use ssh-dir
        if self.ssh_config_file == self.ssh_dir / "config":
            proxy_command += f" --ssh-dir {self.ssh_dir}"
        else:
            # Non-standard config file location, use ssh-config
            proxy_command += f" --ssh-config {self.ssh_config_file}"
            
        return proxy_command
        
    def _build_auth_config(self) -> str:
        """Build the authentication configuration block.
        
        Returns:
            str: SSH config authentication section
        """
        if self.use_1password:
            # When using 1Password:
            # 1. Set IdentityAgent to the 1Password socket (literal tilde for SSH compatibility)
            # 2. Set IdentityFile to the PUBLIC key (.pub) to limit key search
            # 3. Set IdentitiesOnly to yes to avoid using ssh-agent keys
            return """    IdentityAgent ~/.1password/agent.sock
    IdentityFile {}.pub
    IdentitiesOnly yes
""".format(self.ssh_key_file)
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
# Created by cloudX-proxy v{version} on {timestamp}
# Configuration type: generic
Host {self.ssh_host_prefix}-*
    User ec2-user
    TCPKeepAlive yes
"""
        
        # Add SSH multiplexing configuration
        # On Windows, the default SSH client doesn't support Control* options,
        # so we comment them out by default. Users with alternative SSH clients
        # (like the one from Git for Windows) can uncomment these if needed.
        control_path = "~/.ssh/control/%r@%h:%p"
        is_windows = platform.system() == 'Windows'
        comment_prefix = "# " if is_windows else ""
        
        config += f"""    {comment_prefix}ControlMaster auto
    {comment_prefix}ControlPath {control_path}
    {comment_prefix}ControlPersist 4h
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
# Created by cloudX-proxy v{version} on {timestamp}
# Configuration type: environment
Host {self.ssh_host_prefix}-{cloudx_env}-*
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
# Created by cloudX-proxy v{version} on {timestamp}
# Configuration type: host
Host {self.ssh_host_prefix}-{cloudx_env}-{hostname}
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
            host_pattern = f"{self.ssh_host_prefix}-{cloudx_env}-{hostname}"
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
        pattern = f"{self.ssh_host_prefix}-*"
        if self._check_config_exists(pattern, current_config):
            self.print_status(f"Found existing generic config for {pattern}", True, 2)
            return True, current_config
        
        self.print_status(f"Creating generic config for {pattern}", None, 2)
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
        pattern = f"{self.ssh_host_prefix}-{cloudx_env}-*"
        if self._check_config_exists(pattern, current_config):
            self.print_status(f"Found existing config for {pattern}", True, 2)
            
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
                env_config, remaining_config = self._extract_host_config(pattern, current_config)
                
                # Create new environment config
                env_config = self._build_environment_config(cloudx_env)
                
                # Append new environment config to remaining config
                updated_config = remaining_config
                if updated_config and not updated_config.endswith('\n'):
                    updated_config += '\n'
                updated_config += env_config
                
                return True, updated_config
            
            return True, current_config
        
        self.print_status(f"Creating environment config for {pattern}", None, 2)
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
        
        if self.dry_run:
            self.print_status(f"[DRY RUN] Would set up SSH configuration with three-tier approach")
            self.print_status(f"[DRY RUN] Would create generic pattern: {self.ssh_host_prefix}-*", None, 2)
            self.print_status(f"[DRY RUN] Would create environment pattern: {self.ssh_host_prefix}-{cloudx_env}-*", None, 2)
            self.print_status(f"[DRY RUN] Would create host entry: {self.ssh_host_prefix}-{cloudx_env}-{hostname} -> {instance_id}", None, 2)
            self.print_status(f"[DRY RUN] Would write configuration to: {self.ssh_config_file}", None, 2)
            return True
        
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
            self.print_status(f"Adding/updating host entry for {self.ssh_host_prefix}-{cloudx_env}-{hostname}", None, 2)
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
                # Insert before any Host blocks to avoid the Include becoming part of a Host block
                include_line = f"Include {self.ssh_config_file}"

                if system_config_path.exists():
                    content = system_config_path.read_text()

                    # Check if Include already exists
                    if include_line in content:
                        self.print_status("System SSH config already includes our config", True, 2)
                    else:
                        # Find the first Host or Match block
                        lines = content.splitlines()
                        insert_position = None

                        for i, line in enumerate(lines):
                            stripped = line.strip()
                            if stripped.startswith('Host ') or stripped.startswith('Match '):
                                # Found first Host or Match block, insert before it
                                insert_position = i
                                break

                        if insert_position is not None:
                            # Insert before the first Host/Match block
                            lines.insert(insert_position, include_line)
                            # Add a blank line after for readability
                            lines.insert(insert_position + 1, "")
                            new_content = "\n".join(lines)
                        else:
                            # No Host blocks found, append at end with proper spacing
                            new_content = content.rstrip() + "\n\n" + include_line + "\n"

                        system_config_path.write_text(new_content)
                        self.print_status("Added include line to system SSH config", True, 2)

                    # Set correct permissions on system config file
                    if platform.system() != 'Windows':
                        import stat
                        system_config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions
                        self.print_status("Set system config file permissions to 600", True, 2)
                else:
                    system_config_path.write_text(include_line + "\n")
                    self.print_status("Created system SSH config with include line", True, 2)

                    # Set correct permissions on newly created system config file
                    if platform.system() != 'Windows':
                        import stat
                        system_config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions
                        self.print_status("Set system config file permissions to 600", True, 2)

            self.print_status("SSH configuration summary:", None)
            self.print_status(f"System config: {format_path(str(system_config_path))}", None, 2)
            self.print_status(f"cloudX-proxy config: {format_path(str(self.ssh_config_file))}", None, 2)
            self.print_status(f"SSH key directory: {format_path(str(self.ssh_dir))}", None, 2)
            self.print_status(f"Connect using: {format_command(f'ssh {self.ssh_host_prefix}-{cloudx_env}-{hostname}')}", None, 2)
            
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
        ssh_host = f"{self.ssh_host_prefix}-{cloudx_env}-{hostname}"
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
        
        if self.dry_run:
            self.print_status(f"[DRY RUN] Would check instance accessibility for: {hostname}")
            self.print_status(f"[DRY RUN] Would test connection to instance: {instance_id}", None, 2)
            self.print_status(f"[DRY RUN] Would wait up to 5 minutes for SSH access if needed", None, 2)
            return True
        
        # On Windows, skip the automated connection test as it may hang
        # Instead, provide clear instructions for manual testing
        if platform.system() == 'Windows':
            self.print_status("Skipping automated connection test on Windows", None, 2)
            print(f"\n{info('='*60)}")
            print(info("Setup completed! To test your SSH connection, run:"))
            print(f"\n  {format_command(f'ssh {self.ssh_host_prefix}-{cloudx_env}-{hostname}')}")
            print(f"\n{info('='*60)}\n")
            self.print_status("Configuration files have been created successfully", True, 2)
            return True
        
        # On non-Windows systems, proceed with automated connection test
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

    def migrate_to_cloudx(self, target_dir: Path = None) -> bool:
        """Migrate from ~/.ssh/vscode to ~/.ssh/cloudX (or specified target).
        
        Args:
            target_dir: Target directory (default: ~/.ssh/cloudX)
            
        Returns:
            bool: True if migration was successful
        """
        if not target_dir:
            target_dir = Path(self.home_dir) / ".ssh" / "cloudX"
            
        vscode_dir = Path(self.home_dir) / ".ssh" / "vscode"
        
        self.print_header("Migration")
        
        if self.dry_run:
            self.print_status(f"[DRY RUN] Would migrate from {vscode_dir} to {target_dir}")
            self.print_status(f"[DRY RUN] Would update ~/.ssh/config to include new config path", None, 2)
            return True
            
        if not vscode_dir.exists():
            self.print_status(f"Source directory {vscode_dir} does not exist", False, 2)
            return False
            
        if target_dir.exists():
            self.print_status(f"Target directory {target_dir} already exists", False, 2)
            return False
            
        try:
            # Rename directory
            self.print_status(f"Renaming {vscode_dir} to {target_dir}...", None, 2)
            vscode_dir.rename(target_dir)
            self.print_status("Directory renamed successfully", True, 2)
            
            # Update system SSH config
            system_config_path = Path(self.home_dir) / ".ssh" / "config"
            if system_config_path.exists():
                content = system_config_path.read_text()
                
                # Remove old include
                lines = content.splitlines()
                new_lines = []
                include_removed = False
                
                for line in lines:
                    if "Include" in line and "vscode/config" in line:
                        include_removed = True
                        continue
                    new_lines.append(line)
                
                # Add new include
                new_include = f"Include {target_dir}/config"
                if new_include not in content:
                    new_lines.append(new_include)
                    
                system_config_path.write_text("\n".join(new_lines) + "\n")
                
                if include_removed:
                    self.print_status("Updated ~/.ssh/config: Removed old Include, added new Include", True, 2)
                else:
                    self.print_status("Updated ~/.ssh/config: Added new Include", True, 2)
            
            # Update internal state
            self.ssh_dir = target_dir
            self.ssh_config_file = self.ssh_dir / "config"
            self.ssh_key_file = self.ssh_dir / f"{self.ssh_key}"
            
            return True
            
        except Exception as e:
            self.print_status(f"Migration failed: {str(e)}", False, 2)
            return False

    def check_and_perform_migration(self) -> bool:
        """Check if migration is needed and perform it if user agrees.
        
        Returns:
            bool: True if migration was performed, False otherwise
        """
        if not self.pending_migration:
            return False
            
        self.print_header("Migration Available")
        self.print_status("Found existing configuration in ~/.ssh/vscode", None, 2)
        self.print_status("The default directory is now ~/.ssh/cloudX", None, 2)
        
        if self.non_interactive:
            self.print_status("Skipping migration in non-interactive mode", None, 2)
            return False
            
        should_migrate = self.prompt("Do you want to migrate to ~/.ssh/cloudX?", "Y").lower() != 'n'
        
        if should_migrate:
            if self.migrate_to_cloudx():
                self.pending_migration = False
                return True
        
        self.print_status("Continuing with existing ~/.ssh/vscode configuration", None, 2)
        
        # Revert to legacy defaults if using new defaults and migration was declined
        # This ensures we continue to work with vscode defaults in legacy mode
        if self.profile == "cloudX":
            self.profile = "vscode"
            self.print_status("Using legacy profile 'vscode'", None, 2)
            
        if self.ssh_key == "cloudX":
            self.ssh_key = "vscode"
            self.print_status("Using legacy SSH key 'vscode'", None, 2)
            
        return False
