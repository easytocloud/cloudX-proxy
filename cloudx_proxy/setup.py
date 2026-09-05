import os
import platform
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import ClassVar

import boto3
from botocore.exceptions import ClientError

from . import __version__
from ._op import (
    OP_TIMEOUT,
    check_op_cli,
    create_ssh_key,
    get_vaults,
    list_ssh_keys,
    save_public_key,
)
from .colors import error as color_error
from .colors import format_command, format_path, header, info, status_symbol, warning
from .colors import prompt as color_prompt


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

    # Names that end up inside an SSH 'Host' pattern. Whitespace would split
    # one Host line into several aliases, '#' would start a comment, and the
    # glob characters would silently widen the pattern.
    SSH_NAME_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')

    @classmethod
    def validate_ssh_name(cls, name: str | None) -> bool:
        """Validate a name that is written into the SSH configuration.

        Environment names and hostnames become part of a 'Host' line, and the
        hostname default is read from an EC2 tag, so it is not necessarily
        input the user typed. Restrict them to characters that cannot change
        the meaning of the generated config.

        Args:
            name: Environment name or hostname to validate; None and empty are
                invalid, since a prompt with no default yields them

        Returns:
            bool: True if valid, False otherwise
        """
        if not name:
            return False

        return bool(cls.SSH_NAME_PATTERN.match(name))

    @staticmethod
    def quote_shell_argument(value: str) -> str:
        """Quote a ProxyCommand argument so a path containing spaces survives.

        ssh hands ProxyCommand to a shell: /bin/sh on Unix, cmd.exe on Windows.
        Values that need no quoting are returned unchanged, so ordinary configs
        are unaffected.

        Args:
            value: The argument to quote

        Returns:
            str: The argument, quoted if it needs to be
        """
        text = str(value)

        if platform.system() == 'Windows':
            # cmd.exe understands double quotes, not the POSIX single-quote form
            return f'"{text}"' if (not text or re.search(r'\s', text)) else text

        return shlex.quote(text)

    @staticmethod
    def quote_config_value(value: str) -> str:
        """Quote an SSH config directive value that contains whitespace.

        This is ssh_config(5) quoting, not shell quoting: ssh reads double
        quotes around an argument containing spaces. Values that need no
        quoting are returned unchanged.

        Args:
            value: The directive value to quote

        Returns:
            str: The value, quoted if it needs to be
        """
        text = str(value)
        return f'"{text}"' if re.search(r'\s', text) else text

    def get_instance_tags(self, instance_id: str) -> tuple[str | None, str | None]:
        """Fetch instance tags and extract environment and hostname.

        Queries EC2 for the instance tags and extracts:
        - Environment by priority: {env} from Name tag > cloudX:environment tag > Environment tag
        - Hostname from the 'Name' tag (expects format: cloudX-{env}-{hostname} | {username})

        Args:
            instance_id: The EC2 instance ID

        Returns:
            Tuple[Optional[str], Optional[str]]: (environment, hostname) or (None, None) on failure
        """
        if self.dry_run:
            self.print_status(
                f"[DRY RUN] Would fetch tags for {instance_id} to derive environment and hostname",
                None,
                2
            )
            return None, None

        self.print_status("Fetching instance tags...", None, 2)

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

            # Extract hostname and env from Name tag
            # Format: cloudX-{env}-{hostname} | {username}
            hostname = None
            env_from_name = None
            name_tag = tags.get('Name', '')
            if name_tag:
                ssh_hostname = name_tag.split(' | ')[0].strip()
                match = re.match(r'^cloud[xX]-([^-]+)-(.+)$', ssh_hostname)
                if match:
                    env_from_name = match.group(1)
                    hostname = match.group(2)
                    self.print_status(f"Found hostname from Name tag: {hostname}", True, 2)
                else:
                    self.print_status(f"Name tag '{name_tag}' does not match cloudX-{{env}}-{{hostname}} format", None, 2)

            # Determine environment by priority:
            # 1. {env} from Name tag
            # 2. cloudX:environment or cloudx:environment tag
            # 3. Environment tag
            environment = (
                env_from_name
                or tags.get('cloudX:environment')
                or tags.get('cloudx:environment')
                or tags.get('Environment')
            )
            if environment:
                self.print_status(f"Found environment: {environment}", True, 2)

            return environment, hostname

        except ClientError as e:
            self.print_status(f"Error fetching instance tags: {e.response['Error']['Message']}", False, 2)
            return None, None
        except Exception as e:
            self.print_status(f"Error fetching instance tags: {e!s}", False, 2)
            return None, None
    
    def __init__(self, profile: str = "cloudX", ssh_key: str = "cloudX", ssh_config: str | None = None,
                 ssh_dir: str | None = None, aws_env: str | None = None, op_vault: str | None = None, instance_id: str | None = None,
                 ssh_host_prefix: str = "cloudx", non_interactive: bool = False, dry_run: bool = False):
        """Initialize cloudx-proxy setup.
        
        Args:
            profile: AWS profile name (default: "cloudX")
            ssh_key: SSH key name (default: "cloudX")
            ssh_config: SSH config file path (default: None)
            ssh_dir: Directory for SSH keys and config (default: None)
            aws_env: AWS environment directory (default: None)
            op_vault: 1Password vault to use for the SSH key, which also
                turns the 1Password SSH agent on. None or False disables it,
                True or "true" selects the default "Private" vault, and any
                other string names the vault. Holds a vault name, never a
                credential.
            instance_id: EC2 instance ID to set up connection for (optional)
            ssh_host_prefix: Prefix for SSH hosts (default: "cloudx")
            non_interactive: Non-interactive mode, use defaults for all prompts (default: False)
            dry_run: Preview mode, show what would be done without executing (default: False)
        """
        self.profile = profile
        self.ssh_key = ssh_key
        self.aws_env = aws_env
        self.ssh_host_prefix = ssh_host_prefix
        
        # Handle 1Password integration. The flag arrives as None, as a bool,
        # or as a vault name; note that False must disable it, not enable it.
        # These are named op_* rather than *_1password on purpose - see the
        # naming rule at the top of _op.py.
        if op_vault is None or op_vault is False:
            self.op_enabled = False
            self.op_vault = None
        elif op_vault is True or str(op_vault).lower() == 'true':
            self.op_enabled = True
            self.op_vault = "Private"  # Default vault
        else:
            self.op_enabled = True
            self.op_vault = op_vault
        self.instance_id = instance_id
        self.non_interactive = non_interactive
        self.dry_run = dry_run
        self.home_dir = str(Path.home())
        self.op_agent_sock = Path(self.home_dir) / ".1password" / "agent.sock"
        self.op_agent_sock_macos = Path(self.home_dir) / "Library" / "Group Containers" / "2BUA8C4S2C.com.1password" / "t" / "agent.sock"
        # The Linux snap package keeps its agent inside the snap's own home
        # rather than at ~/.1password/agent.sock.
        self.op_agent_sock_snap = Path(self.home_dir) / "snap" / "1password" / "current" / ".1password" / "agent.sock"
        # Set by _check_op_agent() when the agent was found somewhere other
        # than the default socket. None means "write the default".
        self.op_agent_override = None
        
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
        # Name of the host entry last written, which is not necessarily the
        # configured case: an entry already in the config keeps its own name.
        self.last_host_entry_name = None

    # On Windows the 1Password SSH agent serves the standard OpenSSH named
    # pipe, which ssh talks to by default. There is no socket file to find
    # and no IdentityAgent directive to write.
    OP_AGENT_PIPE_WINDOWS = r'\\.\pipe\openssh-ssh-agent'

    def _windows_agent_pipe_exists(self) -> bool:
        """Check whether an SSH agent is listening on the standard OpenSSH pipe."""
        pipe_name = self.OP_AGENT_PIPE_WINDOWS.rsplit('\\', 1)[-1]
        try:
            return pipe_name in os.listdir(r'\\.\pipe')
        except OSError:
            # Enumerating the pipe namespace is not guaranteed to work; fall
            # back to probing the pipe directly.
            return os.path.exists(self.OP_AGENT_PIPE_WINDOWS)

    def _check_op_agent(self) -> bool:
        """Check that the 1Password SSH agent is reachable on this platform.

        Sets self.op_agent_override when the agent was found somewhere other
        than ~/.1password/agent.sock, so the SSH config points at the socket
        that actually exists.

        Returns:
            bool: True if an agent was found.
        """
        system = platform.system()

        if system == 'Windows':
            if not self._windows_agent_pipe_exists():
                self.print_status(
                    f"No SSH agent listening on {self.OP_AGENT_PIPE_WINDOWS}", False, 2
                )
                self.print_status(
                    "Enable the SSH agent in 1Password: Settings > Developer > Use the SSH agent",
                    None,
                    2,
                )
                self.print_status("1Password integration is not supported in this configuration", False, 2)
                return False
            self.print_status("1Password SSH agent pipe is available", True, 2)
            return True

        if self.op_agent_sock.exists():
            if system == 'Darwin' and self.op_agent_sock.is_symlink():
                try:
                    current_target = self.op_agent_sock.resolve(strict=False)
                except FileNotFoundError:
                    current_target = None

                if current_target != self.op_agent_sock_macos and self.op_agent_sock_macos.exists():
                    self.print_status("Updating 1Password agent symlink to default location", None, 2)
                    if not self._ensure_op_agent_symlink():
                        self.print_status("1Password integration is not supported in this configuration", False, 2)
                        return False

            self.print_status("1Password SSH agent socket is available", True, 2)
            return True

        self.print_status("1Password SSH agent socket not found at ~/.1password/agent.sock", False, 2)

        if system == 'Darwin':
            if self._ensure_op_agent_symlink():
                self.print_status("1Password SSH agent socket is available", True, 2)
                return True
        elif self.op_agent_sock_snap.exists():
            # Snap install: use the snap's socket where it is rather than
            # symlinking into a home directory the snap does not see.
            self.op_agent_override = "~/snap/1password/current/.1password/agent.sock"
            self.print_status("Using the snap 1Password SSH agent socket", True, 2)
            return True

        self.print_status("1Password SSH agent is not available", False, 2)
        self.print_status("Please ensure 1Password SSH agent is enabled in 1Password settings", None, 2)
        self.print_status("1Password integration is not supported in this configuration", False, 2)
        return False

    def _op_identity_agent(self) -> str | None:
        """The IdentityAgent value for the 1Password agent, or None to omit it.

        Nothing is written on Windows: ssh reaches the 1Password agent over the
        standard OpenSSH named pipe without being told to, and pointing
        IdentityAgent at a Unix socket path there would aim ssh at nothing and
        break an agent that already works.
        """
        if platform.system() == 'Windows':
            return None
        # A literal tilde, left for ssh to expand.
        return self.op_agent_override or "~/.1password/agent.sock"

    def _ensure_op_agent_symlink(self) -> bool:
        """Ensure ~/.1password/agent.sock points to the macOS agent location."""
        if platform.system() != 'Darwin':
            return False

        if not self.op_agent_sock_macos.exists():
            self.print_status(
                "macOS default 1Password agent socket not found at ~/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock",
                False,
                2,
            )
            return False

        try:
            self.op_agent_sock.parent.mkdir(parents=True, exist_ok=True)

            if self.op_agent_sock.exists() or self.op_agent_sock.is_symlink():
                try:
                    current_target = self.op_agent_sock.resolve(strict=False)
                except FileNotFoundError:
                    current_target = None

                if self.op_agent_sock.is_symlink() and current_target == self.op_agent_sock_macos:
                    self.print_status("1Password agent symlink already points to default location", True, 2)
                    return True

                if not self.op_agent_sock.is_symlink():
                    # Not a symlink: 1Password can be configured to put its
                    # agent here directly, so this may be a live socket. Do not
                    # delete someone's running agent without being told to.
                    self.print_status(
                        f"{self.op_agent_sock} exists and is not a symlink", False, 2
                    )
                    self.print_status(
                        "A running 1Password agent may be listening on it", None, 2
                    )
                    if self.non_interactive:
                        self.print_status(
                            "Refusing to replace it in non-interactive mode", False, 2
                        )
                        return False
                    if self.prompt(
                        "Replace it with a symlink to the macOS agent socket?", "N"
                    ).lower() != 'y':
                        self.print_status("Leaving the existing socket in place", None, 2)
                        return False

                self.print_status("Replacing existing 1Password agent socket entry", None, 2)
                self.op_agent_sock.unlink(missing_ok=True)

            self.op_agent_sock.symlink_to(self.op_agent_sock_macos)
            self.print_status("Created symlink to 1Password agent socket", True, 2)
            return True
        except Exception as e:
            self.print_status(f"Failed to create symlink: {e!s}", False, 2)
            return False

    def print_header(self, text: str) -> None:
        """Print a section header.

        One blank line separates it from what came before. The caller printing
        the banner above the first section does not add one of its own, or the
        two stack into a gap.

        Args:
            text: The header text
        """
        print(f"\n{header(f'=== {text} ===')}")

    def print_status(self, message: str, status: bool | None = None, indent: int = 0) -> None:
        """Print a status message with optional checkmark/cross.

        Args:
            message: The message to print
            status: True for success (✓), False for failure (✗), None for no symbol
            indent: Number of spaces to indent
        """
        prefix = " " * indent
        print(f"{prefix}{status_symbol(status)} {message}")

    def confirm_continue_after_error(self, context: str) -> bool:
        """Ask whether to carry on after a failure, or give up if nobody can answer.

        Recovery prompts default to "yes", which is right when a person is
        watching and can judge the damage. In non-interactive mode there is
        nobody to ask, and answering on the user's behalf turns a failure into
        a successful-looking run: setup reports success and exits 0 having
        written nothing. Fail instead, so the caller sees what happened.

        Args:
            context: Short description of what went wrong, for the message

        Returns:
            bool: True to continue, False to abort
        """
        if self.non_interactive:
            self.print_status(
                f"Cannot continue past {context} in non-interactive mode", False, 2
            )
            return False

        if self.prompt("Would you like to continue anyway?", "Y").lower() == 'n':
            return False

        self.print_status(f"Continuing setup despite {context}", None, 2)
        return True

    def prompt(self, message: str, default: str | None = None) -> str:
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
        prompt_text = f"{color_prompt(message)} [{default}]: " if default else f"{color_prompt(message)}: "
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
            self.print_status(f"Error setting permissions: {e!s}", False, 2)
            return False

    # Tools that must be on PATH for a connection to work, with the page that
    # explains how to install each one
    REQUIRED_TOOLS: ClassVar[dict[str, str]] = {
        'aws': "https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html",
        'session-manager-plugin': "https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html",
    }

    def check_prerequisites(self) -> bool:
        """Check for the external tools a connection depends on.

        Both are invoked from inside the SSH ProxyCommand, where a 'command not
        found' is easy to miss - VSCode reports only that it could not connect -
        so they are reported here, while there is somewhere to show them.

        Returns:
            bool: True if every required tool was found
        """
        self.print_header("Prerequisites")

        if self.dry_run:
            for tool in self.REQUIRED_TOOLS:
                self.print_status(f"[DRY RUN] Would check for {tool}", None, 2)
            return True

        all_found = True
        for tool, install_url in self.REQUIRED_TOOLS.items():
            name = f"{tool}.exe" if platform.system() == 'Windows' and tool == 'aws' else tool
            location = shutil.which(name)
            if location:
                self.print_status(f"{name} found at {format_path(location)}", True, 2)
                continue

            all_found = False
            self.print_status(f"{name} not found on PATH", False, 2)
            self.print_status(f"Install it from {install_url}", None, 2)

        if not all_found:
            self.print_status(
                warning("Setup will continue, but connections will fail until these are installed"),
                None,
                2
            )

        return all_found

    def setup_aws_profile(self) -> bool:
        """Set up AWS profile using aws configure command.
        
        Returns:
            bool: True if profile was set up successfully or user chose to continue
        """
        if self.dry_run:
            self.print_status(f"[DRY RUN] Would check AWS profile configuration for '{self.profile}'")
            if self.aws_env:
                self.print_status(f"[DRY RUN] Would configure AWS environment: {self.aws_env}", None, 2)
            self.print_status("[DRY RUN] Would verify AWS credentials and extract cloudX environment", None, 2)
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
            except Exception:
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
            self.print_status(f"{color_error('Error:', bold=True)} {e!s}", False, 2)
            return False

    def _check_op_availability(self) -> bool:
        """Check if 1Password CLI and SSH agent are available.
        
        Returns:
            bool: True if 1Password is available and configured
        """
        if not self.op_enabled:
            return False
            
        self.print_status("Checking 1Password availability...")
        
        # Use our helper function to check 1Password CLI
        installed, authenticated, version = check_op_cli()
        
        if not installed:
            self.print_status("1Password CLI not found. Please install it from https://1password.com/downloads/command-line/", False, 2)
            return False
        
        self.print_status(f"1Password CLI {version} installed", True, 2)
        
        if not authenticated:
            self.print_status("1Password CLI is not authenticated. Run 'op signin' first.", False, 2)
            return False
        
        self.print_status("1Password CLI is authenticated", True, 2)
        
        # Check that the 1Password SSH agent is reachable. Where it lives is
        # platform-specific, so this is not a single path test.
        if not self._check_op_agent():
            return False
        
        # If using a vault other than "Private", warn the user
        if self.op_vault and self.op_vault != "Private":
            self.print_status(warning(f"Warning: Using vault '{self.op_vault}' instead of default 'Private' vault"), None, 2)
            self.print_status(warning("Make sure to enable this vault for SSH in 1Password settings"), None, 2)
            self.print_status(warning("By default, only the 'Private' vault is enabled for SSH"), None, 2)
        
        return True

    def _create_op_key(self) -> bool:
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
                    check=False,
                    timeout=OP_TIMEOUT
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
                    self.print_status("Failed to retrieve public key from 1Password", False, 2)
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
                    print(f"\n{info('Available 1Password vaults:')}")
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
                print(f"\n{info('Available 1Password vaults:')}")
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
            success, public_key, _item_id = create_ssh_key(ssh_key_title_with_prefix, selected_vault)
            
            if not success:
                self.print_status("Failed to create SSH key in 1Password", False, 2)
                return False
            
            self.print_status("SSH key created successfully in 1Password", True, 2)
            
            # Save the public key to the expected location
            if not save_public_key(public_key, f"{self.ssh_key_file}.pub"):
                self.print_status(f"Failed to save public key to {self.ssh_key_file}.pub", False, 2)
                return False

            self.print_status(f"Saved public key to {self.ssh_key_file}.pub", True, 2)

            # Remind user to enable the key in 1Password SSH agent
            self.print_status(warning("Important: Make sure the key is enabled in 1Password's SSH agent settings"), None, 2)
            return True

        except Exception as e:
            self.print_status(f"Error creating key in 1Password: {e!s}", False, 2)
            return False

    def setup_ssh_key(self) -> bool:
        """Set up SSH key pair.
        
        Returns:
            bool: True if key was set up successfully
        """
        self.print_header("SSH Key Configuration")
        
        if self.dry_run:
            self.print_status(f"[DRY RUN] Would check SSH key '{self.ssh_key}' configuration")
            if self.op_enabled:
                self.print_status("[DRY RUN] Would use 1Password SSH agent for authentication", None, 2)
                self.print_status(f"[DRY RUN] Would create or find SSH key in vault: {self.op_vault}", None, 2)
            else:
                self.print_status(f"[DRY RUN] Would create SSH key pair at: {self.ssh_key_file}", None, 2)
                self.print_status("[DRY RUN] Would set proper file permissions", None, 2)
            return True
        
        # Check 1Password integration if requested
        if self.op_enabled:
            op_available = self._check_op_availability()
            if op_available:
                self.print_status("Using 1Password SSH agent for authentication", True, 2)
                
                # Always prefer to create keys in 1Password
                return self._create_op_key()
            else:
                # 1Password was asked for explicitly. Falling back to an
                # on-disk key changes the authentication mechanism, so in
                # non-interactive mode say so rather than quietly substituting
                # one and reporting success.
                if self.non_interactive:
                    self.print_status(
                        "1Password was requested but is not available; "
                        "refusing to fall back to an on-disk key in non-interactive mode",
                        False,
                        2
                    )
                    return False

                proceed = self.prompt("1Password integration not available. Continue with standard SSH key setup?", "Y").lower() != "n"
                if not proceed:
                    return False
                self.op_enabled = False  # Fallback to standard setup
        
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
            self.print_status(f"Error: {e!s}", False, 2)
            return self.confirm_continue_after_error("SSH key issues")

    def _build_proxy_command(self) -> str:
        """Build the ProxyCommand with appropriate parameters.

        Suppresses redundant flags that match auto-detected defaults to keep
        the SSH config clean. The connect command will auto-detect these values
        if not provided. Environment-specific flags (like --aws-env) are always
        preserved.

        Returns:
            str: The complete ProxyCommand string
        """
        # Use the same case as ssh_host_prefix for the proxy command
        # If prefix is "cloudX", use "cloudX-proxy"; if "cloudx", use "cloudx-proxy"
        prefix_base = self.ssh_host_prefix.split('-')[0] if '-' in self.ssh_host_prefix else self.ssh_host_prefix
        proxy_command = f"uvx {prefix_base}-proxy connect %h %p"

        # Always include aws-env if specified (environment-specific, cannot be auto-detected)
        if self.aws_env:
            proxy_command += f" --aws-env {self.quote_shell_argument(self.aws_env)}"

        # Determine what the auto-detected defaults would be for this environment
        # Default profile and ssh-key based on directory: cloudX > vscode > cloudX
        cloudx_dir = Path(self.home_dir) / ".ssh" / "cloudX"
        vscode_dir = Path(self.home_dir) / ".ssh" / "vscode"

        if cloudx_dir.exists():
            default_profile, default_ssh_key = "cloudX", "cloudX"
        elif vscode_dir.exists():
            default_profile, default_ssh_key = "vscode", "vscode"
        else:
            default_profile, default_ssh_key = "cloudX", "cloudX"

        # Only include profile if it differs from the auto-detected default
        if self.profile != default_profile:
            proxy_command += f" --profile {self.quote_shell_argument(self.profile)}"

        # Only include ssh-key if it differs from the auto-detected default
        if self.ssh_key != default_ssh_key:
            proxy_command += f" --ssh-key {self.quote_shell_argument(self.ssh_key)}"

        # Only include ssh-dir if it's non-standard (not ~/.ssh/cloudX or ~/.ssh/vscode)
        standard_cloudx = cloudx_dir / "config"
        standard_vscode = vscode_dir / "config"

        if self.ssh_config_file not in (standard_cloudx, standard_vscode):
            # Non-standard config file location, include ssh-config
            proxy_command += f" --ssh-config {self.quote_shell_argument(self.ssh_config_file)}"

        return proxy_command
        
    def _build_auth_config(self) -> str:
        """Build the authentication configuration block.

        Returns:
            str: SSH config authentication section
        """
        if self.op_enabled:
            # When using 1Password:
            # 1. Point IdentityAgent at the 1Password socket, where one has to
            #    be named at all - see _op_identity_agent()
            # 2. Set IdentityFile to the PUBLIC key (.pub) to limit key search.
            #    IdentitiesOnly yes is set globally for all cloudX hosts, and
            #    ssh offers only identities named by IdentityFile even when the
            #    agent holds more - so the .pub is what lets the agent's copy of
            #    the key be used at all.
            lines = []
            identity_agent = self._op_identity_agent()
            if identity_agent:
                lines.append(f"    IdentityAgent {identity_agent}")
            lines.append(
                f"    IdentityFile {self.quote_config_value(f'{self.ssh_key_file}.pub')}"
            )
            return "\n".join(lines) + "\n"
        else:
            # Standard SSH key configuration
            # (IdentitiesOnly is now set globally for all cloudX hosts)
            return f"""    IdentityFile {self.quote_config_value(self.ssh_key_file)}
"""

    # Matches the start of an SSH config section. SSH keywords are
    # case-insensitive, so 'host', 'Host' and 'HOST' all open a block.
    _SECTION_KEYWORD_RE = re.compile(r'^\s*(host|match)\s+(.*)$', re.IGNORECASE)

    def _split_config_blocks(self, config_content: str) -> tuple[list, list, list]:
        """Split an SSH config into a preamble and Host/Match blocks.

        Comment and blank lines that trail a block are held back and attached to
        the block that follows them, so a comment written above a Host entry
        travels with that entry (and so the generated banners, which always sit
        above the section they label, are dropped along with it).

        Args:
            config_content: SSH config file content

        Returns:
            Tuple[list, list, list]: (preamble lines, blocks, trailing lines),
            where each block is a dict with 'keyword', 'value', 'lines' (raw,
            starting with the header line) and 'leading' (comments above it).
        """
        preamble = []
        blocks = []
        current = None
        pending = []  # comment/blank lines awaiting the next directive or block

        for line in config_content.split('\n'):
            match = self._SECTION_KEYWORD_RE.match(line)
            if match:
                if current is not None:
                    blocks.append(current)
                current = {
                    'keyword': match.group(1).lower(),
                    'value': match.group(2).strip(),
                    'lines': [line],
                    'leading': pending,
                }
                pending = []
                continue

            if not line.strip() or line.strip().startswith('#'):
                pending.append(line)
                continue

            # A directive belongs to the open block, along with anything that
            # was buffered inside that block.
            target = current['lines'] if current is not None else preamble
            target.extend(pending)
            target.append(line)
            pending = []

        if current is not None:
            blocks.append(current)
        else:
            preamble.extend(pending)
            pending = []

        return preamble, blocks, pending

    # Directives this tool writes whose value is a path the user controls, and
    # which may therefore contain whitespace. ssh keywords are case-insensitive.
    _PATH_DIRECTIVE_RE = re.compile(r'^(\s*)(IdentityFile)(\s+)(\S.*)$', re.IGNORECASE)

    @classmethod
    def _requote_path_directive(cls, line: str) -> str:
        """Quote a path-valued directive whose value contains whitespace.

        ssh_config(5) splits a directive's arguments on whitespace unless they
        are double quoted, so `IdentityFile /home/First Last/.ssh/cloudX` does
        not name the file it appears to. Configurations written before that was
        handled still carry the unquoted form, and neither a rewrite nor adding
        a host regenerates the line, so it is repaired in place here.

        The value is wrapped, never rebuilt: a path someone edited by hand stays
        the path they chose. Values that need no quoting, are already quoted, or
        contain a quote of their own are returned untouched.

        Args:
            line: A single configuration line

        Returns:
            str: The line, quoted if it needed it
        """
        match = cls._PATH_DIRECTIVE_RE.match(line)
        if not match:
            return line

        indent, keyword, gap, value = match.groups()
        value = value.rstrip()
        if '"' in value or not re.search(r'\s', value):
            return line

        return f'{indent}{keyword}{gap}"{value}"'

    def _prefix_spellings(self) -> list[str]:
        """The spellings of the host prefix a managed block should answer to.

        The configured one first, then its lowercase form, then - for this
        project's own prefix - the counterpart spelling, so a config written
        as cloudx also answers to cloudX and the other way round.
        """
        spellings = [self.ssh_host_prefix]
        counterpart = 'cloudX' if self.ssh_host_prefix.lower() == 'cloudx' else None
        for candidate in (self.ssh_host_prefix.lower(), counterpart):
            if candidate and candidate not in spellings:
                spellings.append(candidate)
        return spellings

    @property
    def preferred_host_prefix(self) -> str:
        """The spelling to show a pattern in.

        cloudX is the product's own name - the X is ten, after Cloud9 - so it
        is the spelling to put in front of a user, whichever of the two command
        names they happened to type. Any other prefix is shown as configured.
        """
        if self.ssh_host_prefix.lower() == 'cloudx':
            return 'cloudX'
        return self.ssh_host_prefix

    def _host_pattern_variants(self, pattern: str) -> list[str]:
        """Every spelling of a wildcard Host pattern to write, canonical first.

        ssh matches Host patterns case-SENSITIVELY, and its pattern syntax has
        only '*' and '?' - there is no [xX] character class, so `cloud[xX]-*`
        matches a host literally called that and nothing else. A block written
        as `Host cloudX-*` therefore simply does not apply to a host entry
        spelled `cloudx-dev-web1`, and both spellings exist in the wild: they
        have been written by different versions of this tool, by the two
        command names, and by hand.

        A Host line takes any number of patterns and matches if any one of them
        does, so wildcard blocks list every spelling rather than betting on one.

        Args:
            pattern: A Host pattern, e.g. 'cloudX-dev-*'

        Returns:
            list[str]: The patterns to write, canonical spelling first. Only
            the prefix varies; everything after it is left exactly as given.
        """
        prefix_len = len(self.ssh_host_prefix)
        if pattern[:prefix_len + 1].lower() != f"{self.ssh_host_prefix.lower()}-":
            return [pattern]

        rest = pattern[prefix_len:]
        variants = []
        for spelling in self._prefix_spellings():
            candidate = f"{spelling}{rest}"
            if candidate not in variants:
                variants.append(candidate)
        return variants

    def _host_line_value(self, pattern: str) -> str:
        """The Host line value for a pattern: every spelling, space separated."""
        return ' '.join(self._host_pattern_variants(pattern))

    def _collapse_host_patterns(self, patterns: list[str]) -> str | None:
        """Collapse a Host line's patterns to the single pattern they spell.

        Our wildcard blocks carry one pattern per prefix spelling, so their Host
        lines list more than one. That is still one block - but only while the
        patterns differ in case alone. A line naming genuinely different hosts
        is the user's, and stays theirs.

        Args:
            patterns: The whitespace-separated patterns of a Host line

        Returns:
            str | None: The first pattern if they are all one pattern, else None
        """
        if not patterns:
            return None
        if len({pattern.lower() for pattern in patterns}) != 1:
            return None
        return patterns[0]

    def _normalize_managed_host_line(self, line: str) -> str:
        """Write a managed Host line so it matches every spelling of the prefix.

        Blocks are recognised as ours case-insensitively, but ssh matches Host
        patterns case-SENSITIVELY. Writing a block back in the case it happened
        to have therefore produces a file whose parts disagree: a stale
        `Host cloudx-*` sitting above `Host cloudX-dev-web1` never matches it,
        so `IdentitiesOnly yes` and `User ec2-user` silently stop applying -
        which lets ssh offer every agent key and hit the server's MaxAuthTries
        before reaching the one that was just pushed.

        Wildcard blocks are therefore written with one pattern per prefix
        spelling, which covers the mixed-case files already out there instead
        of merely refusing to add to them.

        Host entries are left exactly as they are. `cloudX` is the product's
        name - the X is ten, after Cloud9 - but people who dislike reaching for
        shift call their instance `cloudx-dev-something`, and that name is
        theirs: it is what they type, what `list` reports and what VSCode
        offers. Since the wildcard blocks above now answer to both spellings,
        the entry does not need renaming to pick up its settings.

        Args:
            line: A managed block's Host line

        Returns:
            str: The line with its patterns in canonical form
        """
        match = re.match(r'^(\s*)(host)(\s+)(.*)$', line, re.IGNORECASE)
        if not match:
            return line

        indent, keyword, gap, value = match.groups()

        # Split off an inline comment, keeping the spacing in front of it.
        hash_pos = value.find('#')
        body, tail = (value, '') if hash_pos == -1 else (value[:hash_pos], value[hash_pos:])
        gap_before_comment = body[len(body.rstrip()):]

        collapsed = self._collapse_host_patterns(body.split())
        if collapsed is None:
            return line

        prefix_len = len(self.ssh_host_prefix)
        if collapsed[:prefix_len + 1].lower() != f"{self.ssh_host_prefix.lower()}-":
            return line

        if '*' not in collapsed:
            return line

        canonical = f"{self.ssh_host_prefix}{collapsed[prefix_len:]}"
        patterns = self._host_pattern_variants(canonical)

        return f"{indent}{keyword}{gap}{' '.join(patterns)}{gap_before_comment}{tail}"

    def _clean_managed_lines(self, lines: list) -> list:
        """Strip comments and blank lines from a block cloudx-proxy manages.

        The header line keeps its inline comment, but has its prefix put into
        the case in use; everything below it is normalised, since those
        sections are regenerated from scratch on every write.

        Args:
            lines: Raw lines of the block, header first

        Returns:
            list: Cleaned lines
        """
        cleaned = []
        for index, line in enumerate(lines):
            if index == 0:
                cleaned.append(self._normalize_managed_host_line(line.rstrip()))
                continue
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if '#' in line:
                line = line.split('#')[0].rstrip()
            line = self._requote_path_directive(line)
            cleaned.append(line.rstrip())
        return cleaned

    # A banner this tool generates: a rule line, a title line, a rule line
    _BANNER_RULE_RE = re.compile(r'^#\s*={10,}\s*$')

    @classmethod
    def _strip_generated_banners(cls, lines: list) -> list:
        """Remove banners this tool wrote, so rewrites don't stack them up.

        A preserved block keeps the comments written above it, but the section
        banner we emit above the unmanaged section is one of those comments on
        the next read. Without this it would be re-emitted on every rewrite and
        the file would grow each time cleanup ran.

        Args:
            lines: Lines that may contain a generated banner

        Returns:
            list: The lines with any generated banner removed
        """
        result = []
        index = 0
        while index < len(lines):
            is_banner = (
                index + 2 < len(lines)
                and cls._BANNER_RULE_RE.match(lines[index])
                and lines[index + 1].strip().startswith('#')
                and cls._BANNER_RULE_RE.match(lines[index + 2])
            )
            if is_banner:
                index += 3
                continue
            result.append(lines[index])
            index += 1
        return result

    @classmethod
    def _raw_block_lines(cls, block: dict) -> list:
        """Return an unmanaged block verbatim, including the comments above it."""
        lines = cls._strip_generated_banners(list(block['leading'])) + list(block['lines'])
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return lines

    def _environment_for_host(self, host_name: str, env_names: list) -> str | None:
        """Determine which environment a host entry belongs to.

        Environment names may contain hyphens (e.g. 'pre-prod'), which makes
        '<prefix>-<env>-<hostname>' ambiguous. Environments already declared in
        the config therefore win, longest name first; only when none matches is
        the first segment after the prefix used.

        Args:
            host_name: Host entry name (e.g. 'cloudx-pre-prod-web1')
            env_names: Known environment names, sorted longest first

        Returns:
            Optional[str]: Environment name, or None if the host doesn't fit
        """
        lowered = host_name.lower()
        for env_name in env_names:
            if lowered.startswith(f"{self.ssh_host_prefix}-{env_name}-".lower()):
                return env_name

        match = re.match(
            rf'^{re.escape(self.ssh_host_prefix)}-([^-]+)-.+$', host_name, re.IGNORECASE
        )
        return match.group(1) if match else None

    def _parse_ssh_config(self, config_content: str) -> dict:
        """Parse SSH config into structured sections.

        Returns a dict with:
        - 'version': Version header line (if present)
        - 'global': Global Host cloudX-* section
        - 'environments': Dict with lowercased environment name -> {pattern, name, lines}
        - 'preamble': Directives above the first Host/Match block, which apply
          to every host and must stay above them, kept verbatim
        - 'other': Blocks cloudx-proxy does not manage, kept verbatim so a
          rewrite never discards them

        Args:
            config_content: SSH config file content

        Returns:
            dict: Parsed configuration structure
        """
        result = {
            'version': None,
            'global': None,
            'environments': {},
            'preamble': [],
            'other': []
        }

        preamble, blocks, trailing = self._split_config_blocks(config_content)

        # Extract version header. It sits above the first block, so it is held
        # in that block's leading comments rather than in the preamble; drop it
        # there too, otherwise a rewrite would emit it twice when the first
        # block happens to be one we don't manage.
        leading_of_first = blocks[0]['leading'] if blocks else []
        for source in (preamble, leading_of_first):
            for line in source:
                stripped = line.strip()
                if stripped.startswith('#') and (
                    'Managed by' in stripped or 'SSH Configuration' in stripped
                ):
                    result['version'] = stripped
                    break
            if result['version']:
                break

        if result['version']:
            if blocks:
                blocks[0]['leading'] = [
                    line for line in leading_of_first if line.strip() != result['version']
                ]
            preamble = [line for line in preamble if line.strip() != result['version']]

        # Directives above the first Host/Match block apply to every host, so
        # they have to be kept, and kept above the blocks: moved below one they
        # would silently narrow to whichever host came last.
        result['preamble'] = self._strip_generated_banners(preamble)
        while result['preamble'] and not result['preamble'][0].strip():
            result['preamble'].pop(0)
        while result['preamble'] and not result['preamble'][-1].strip():
            result['preamble'].pop()

        prefix = self.ssh_host_prefix
        global_pattern = f"{prefix}-*".lower()
        env_pattern_re = re.compile(rf'^{re.escape(prefix)}-(.+)-\*$', re.IGNORECASE)

        managed_hosts = []  # (host_name, block) resolved after environments are known
        unmanaged = []

        # First pass: global section and environment patterns. Environment
        # patterns have to be collected before host entries, because they are
        # what makes a hyphenated environment name unambiguous.
        for block in blocks:
            # A wildcard block of ours lists one pattern per prefix spelling,
            # so collapse those back to the single pattern they spell. Match
            # blocks, Host lines naming genuinely different hosts, and anything
            # not carrying our prefix belong to the user, not to us.
            name = None
            if block['keyword'] == 'host':
                name = self._collapse_host_patterns(
                    block['value'].split('#')[0].split()
                )
            if not name:
                unmanaged.append(block)
                continue

            if name.lower() == global_pattern:
                if result['global'] is None:
                    result['global'] = '\n'.join(
                        self._clean_managed_lines(block['lines'])
                    ).strip()
                continue

            env_match = env_pattern_re.match(name)
            if env_match:
                env_name_original = env_match.group(1)  # Preserve original case
                env_name_key = env_name_original.lower()  # Lowercase for case-insensitive matching
                if env_name_key in result['environments']:
                    continue  # Duplicate environment pattern: first one wins
                result['environments'][env_name_key] = {
                    'pattern': f"{prefix}-{env_name_original}-*",
                    'name': env_name_original,  # Store original case for display
                    'lines': self._clean_managed_lines(block['lines'])
                }
                continue

            if name.lower().startswith(f"{prefix}-".lower()) and '*' not in name:
                managed_hosts.append((name, block))
                continue

            unmanaged.append(block)

        # Second pass: attach host entries to their environment
        env_names = sorted(
            (env_data['name'] for env_data in result['environments'].values()),
            key=len,
            reverse=True
        )
        seen_hosts = set()  # Track seen hosts to avoid duplicates

        for host_name, block in managed_hosts:
            env_name_original = self._environment_for_host(host_name, env_names)
            if not env_name_original:
                unmanaged.append(block)
                continue

            # Skip duplicates
            if host_name.lower() in seen_hosts:
                continue
            seen_hosts.add(host_name.lower())

            env_name_key = env_name_original.lower()

            # Create environment if not exists (a host without its pattern)
            if env_name_key not in result['environments']:
                result['environments'][env_name_key] = {
                    'pattern': f"{prefix}-{env_name_original}-*",
                    'name': env_name_original,  # Store original case for display
                    'lines': [
                        f"Host {self._host_line_value(f'{prefix}-{env_name_original}-*')}"
                    ]
                }

            # Add host entry
            result['environments'][env_name_key]['lines'].extend(
                self._clean_managed_lines(block['lines'])
            )

        # Preserve unmanaged blocks in their original order, plus any comment
        # left at the end of the file.
        result['other'] = [self._raw_block_lines(block) for block in unmanaged]
        trailing_comments = [line for line in trailing if line.strip()]
        if trailing_comments:
            result['other'].append(trailing_comments)

        return result

    def _organize_ssh_config(self, global_config: str, environments: dict,
                             other_blocks: list | None = None,
                             preamble: list | None = None) -> str:
        """Organize SSH config with proper structure and banners.

        Args:
            global_config: Global configuration block
            environments: Dict of environment_name -> {pattern, lines}
            other_blocks: Blocks not managed by cloudx-proxy, each a list of
                raw lines, appended verbatim so a rewrite never loses them
            preamble: Directives that appeared above the first Host block; they
                apply to every host, so they are written back above them

        Returns:
            str: Organized SSH config content
        """
        lines = [f"# SSH Configuration - Managed by {self.ssh_host_prefix}-proxy v{__version__}", ""]

        # Anything above the first Host block stays above it
        if preamble:
            lines.extend(preamble)
            lines.append("")

        # Add global section with banner
        if global_config:
            lines.append("# ==============================================================================")
            lines.append("#  GLOBAL")
            lines.append("# ==============================================================================")
            lines.append("")
            lines.extend(global_config.split('\n'))
            lines.append("")

        # Add environment sections in alphabetical order
        for env_key in sorted(environments.keys()):
            env_data = environments[env_key]
            # Use original case name for banner if available
            display_name = env_data.get('name', env_key)
            lines.append("# ==============================================================================")
            lines.append(f"#  {display_name}")
            lines.append("# ==============================================================================")
            lines.append("")

            # Extract environment pattern and its config from lines
            env_pattern_line = None
            env_config_lines = []  # Config lines that belong to the pattern
            host_lines = []
            in_hosts = False
            seen_pattern = False

            for line in env_data['lines']:
                if line.startswith('Host ') and '*' in line:
                    # This is the environment pattern line
                    env_pattern_line = line
                    seen_pattern = True
                elif line.startswith('Host ') and '*' not in line:
                    # This is a host entry - stop collecting pattern config
                    in_hosts = True
                    host_lines.append(line)
                elif in_hosts:
                    # Host entry content
                    host_lines.append(line)
                elif seen_pattern and not in_hosts:
                    # Config content that belongs to the environment pattern
                    # (indented lines after Host pattern-*)
                    env_config_lines.append(line)

            # Add environment pattern line
            if env_pattern_line:
                lines.append(env_pattern_line)
            # Add environment config content (auth, ProxyCommand, etc)
            for line in env_config_lines:
                if line.strip():  # Skip empty lines but preserve indentation
                    lines.append(line)
            if env_pattern_line or env_config_lines:
                lines.append("")

            # Add host entries sorted by hostname
            if host_lines:
                sorted_hosts = []
                current_host = []
                for line in host_lines:
                    if line.startswith('Host ') and current_host:
                        sorted_hosts.append('\n'.join(current_host))
                        current_host = [line]
                    else:
                        current_host.append(line)
                if current_host:
                    sorted_hosts.append('\n'.join(current_host))

                # Sort by hostname (first line)
                sorted_hosts.sort(key=lambda x: x.split('\n')[0])

                for host in sorted_hosts:
                    lines.append(host.rstrip())
                    lines.append("")

        # Append everything we don't manage, untouched and in its original
        # order. These entries are the user's; they are kept last so that our
        # specific patterns are not shadowed by a catch-all such as 'Host *'.
        if other_blocks:
            lines.append("# ==============================================================================")
            lines.append(f"#  NOT MANAGED BY {self.ssh_host_prefix}-proxy - PRESERVED AS-IS")
            lines.append("# ==============================================================================")
            lines.append("")
            for block_lines in other_blocks:
                lines.extend(block_lines)
                lines.append("")

        # Join and clean up
        result = '\n'.join(lines)
        # Remove duplicate empty lines
        while '\n\n\n' in result:
            result = result.replace('\n\n\n', '\n\n')

        return result.rstrip() + '\n'

    def _normalize_prefix(self, content: str) -> str:
        """Normalize all cloudX/cloudx references to match self.ssh_host_prefix.

        This allows users to convert between 'cloudX' and 'cloudx' naming conventions
        by running cleanup with the desired command name (cloudX-proxy or cloudx-proxy).

        Args:
            content: SSH config content or single line

        Returns:
            str: Content with normalized prefix
        """
        # Determine the "other" prefix to replace
        other_prefix = 'cloudx' if self.ssh_host_prefix == 'cloudX' else 'cloudX'

        # Replace in wildcard Host patterns only: Host cloudX-* or Host
        # cloudx-*. A host entry carries no '*', and its name belongs to
        # whoever created the instance - converting the command name must not
        # rename it out from under them.
        content = re.sub(
            rf'\bHost {other_prefix}-(?=\S*\*)',
            f'Host {self.ssh_host_prefix}-',
            content
        )

        # Replace in ProxyCommand: uvx cloudX-proxy or uvx cloudx-proxy
        content = re.sub(
            rf'\buvx {other_prefix}-proxy\b',
            f'uvx {self.ssh_host_prefix}-proxy',
            content
        )

        return content

    def _build_generic_config(self) -> str:
        """Build a generic configuration block with common settings for all environments.

        Returns:
            str: Generic configuration block
        """
        # No metadata comments - handled by _organize_ssh_config
        config = f"""Host {self._host_line_value(f"{self.ssh_host_prefix}-*")}
    User ec2-user
    TCPKeepAlive yes
    IdentitiesOnly yes
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
        # No metadata comments - handled by _organize_ssh_config
        config = f"""Host {self._host_line_value(f"{self.ssh_host_prefix}-{cloudx_env}-*")}
"""
        # Add authentication configuration
        config += self._build_auth_config()

        # Add ProxyCommand
        config += f"""    ProxyCommand {self._build_proxy_command()}
"""

        return config
        
    def _build_host_config(self, cloudx_env: str, hostname: str, instance_id: str,
                           host_name: str | None = None) -> str:
        """Build a host-specific configuration block.

        Args:
            cloudx_env: CloudX environment
            hostname: Hostname for the instance
            instance_id: EC2 instance ID
            host_name: Full name to write, when an entry already exists under a
                name of its own. New entries use the configured prefix.

        Returns:
            str: Host configuration block
        """
        # No metadata comments - handled by _organize_ssh_config
        config = f"""Host {host_name or f"{self.ssh_host_prefix}-{cloudx_env}-{hostname}"}
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
    
    def _add_host_entry(self, cloudx_env: str, instance_id: str, hostname: str, current_config: str) -> bool:
        """Add/update host entry and reorganize config file.

        Parses the config, adds/updates the host entry, and reorganizes the file
        with proper structure and banners.

        Args:
            cloudx_env: CloudX environment
            instance_id: EC2 instance ID
            hostname: Hostname for the instance
            current_config: Current SSH config content

        Returns:
            bool: True if settings were added successfully
        """
        try:
            # Parse existing config
            parsed = self._parse_ssh_config(current_config)

            # Environments are keyed case-insensitively. Adopt the case already
            # in the config, otherwise 'Dev' would create a second section next
            # to an existing 'dev' one, and ssh (whose Host matching IS
            # case-sensitive) would resolve neither reliably.
            env_key = cloudx_env.lower()
            existing_env = parsed['environments'].get(env_key)
            if existing_env:
                cloudx_env = existing_env.get('name', cloudx_env)

            host_pattern = f"{self.ssh_host_prefix}-{cloudx_env}-{hostname}"
            host_existed = False
            existing_host_name = None
            self.last_host_entry_name = host_pattern

            # Ensure environment section exists
            if existing_env is None:
                # Create new environment
                env_pattern = f"{self.ssh_host_prefix}-{cloudx_env}-*"
                parsed['environments'][env_key] = {
                    'pattern': env_pattern,
                    'name': cloudx_env,
                    'lines': [
                        f"Host {self._host_line_value(env_pattern)}",
                        *self._build_environment_config(cloudx_env).split('\n')[1:],
                    ]
                }
                self.print_status(f"Created new environment section for '{cloudx_env}'", None, 2)
            else:
                # Drop any existing entry for this host; it is re-added below
                env_lines = existing_env['lines']
                new_lines = []
                skipping = False
                for line in env_lines:
                    section = self._SECTION_KEYWORD_RE.match(line)
                    if section:
                        entry = section.group(2).split('#')[0].strip()
                        skipping = entry.lower() == host_pattern.lower()
                        if skipping:
                            host_existed = True
                            existing_host_name = entry
                            continue
                    elif skipping:
                        continue
                    new_lines.append(line)
                existing_env['lines'] = new_lines

            # Add new host entry. An entry that is already there keeps the
            # name it has: cloudX is the product's name, but calling the box
            # cloudx-dev-web1 is its owner's call and it is what they type -
            # only the instance id is being updated here.
            self.last_host_entry_name = existing_host_name or host_pattern
            new_host_entry = self._build_host_config(
                cloudx_env, hostname, instance_id, host_name=existing_host_name
            )
            parsed['environments'][env_key]['lines'].extend(new_host_entry.split('\n'))

            # Rebuild config with organization
            organized_config = self._organize_ssh_config(
                parsed['global'] or self._build_generic_config(),
                parsed['environments'],
                parsed['other'],
                parsed['preamble']
            )

            # Write organized config
            self.ssh_config_file.write_text(organized_config)

            # Set proper permissions on the config file
            if platform.system() != 'Windows':
                import stat
                self.ssh_config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions

            if host_existed:
                self.print_status(f"Updated host entry for {host_pattern}", True, 2)
            else:
                self.print_status(f"Added new host entry for {host_pattern}", True, 2)

            return True

        except Exception as e:
            self.print_status(f"{color_error('Error:', bold=True)} {e!s}", False, 2)
            return self.confirm_continue_after_error("SSH config issues")

    # Flags a ProxyCommand can carry, with their values quoted or bare
    _PROXY_FLAG_RE = re.compile(r'''(--[\w-]+)\s+("[^"]*"|'[^']*'|[^\s-]\S*)''')

    def _rebuild_proxy_command(self, line: str) -> str:
        """Rebuild a ProxyCommand, keeping every flag it already carried.

        The rebuild exists to drop flags that merely restate an auto-detected
        default, but it recomputes them from this process's own defaults, which
        are not the ones the line was written with. Left to itself it deletes
        settings that are doing real work: an explicit `--profile cloudx` was
        dropped because the default detected here is `cloudX`, and since AWS
        profile names are case-sensitive the next connection failed with "The
        config profile (cloudX) could not be found".

        A flag the rebuild does not reproduce is therefore carried over rather
        than discarded. Cleanup may tidy the configuration; it may not decide
        that part of it was unnecessary.

        Args:
            line: The existing ProxyCommand line

        Returns:
            str: The rebuilt command, with nothing lost
        """
        existing = dict(self._PROXY_FLAG_RE.findall(line))

        # aws-env cannot be derived from anything here, so it is fed back in
        original_aws_env = self.aws_env
        aws_env = existing.get('--aws-env')
        self.aws_env = aws_env.strip('"\'') if aws_env else None
        try:
            rebuilt = self._build_proxy_command()
        finally:
            self.aws_env = original_aws_env

        for flag, value in existing.items():
            if flag not in rebuilt:
                rebuilt += f" {flag} {value}"

        return rebuilt

    def cleanup_config(self) -> bool:
        """Clean up and reorganize SSH configuration file.

        Reads the entire config file, removes duplicates, reorganizes with
        proper structure, and writes back completely fresh (full rewrite).
        Also rebuilds ProxyCommand to remove unnecessary default flags.

        Returns:
            bool: True if cleanup was successful
        """
        try:
            if not self.ssh_config_file.exists():
                self.print_status(f"SSH config file not found: {self.ssh_config_file}", False, 2)
                return False

            # Read current config
            original_config = self.ssh_config_file.read_text()

            # Normalize prefix (cloudX/cloudx) to match the command being used
            # This allows users to convert between naming conventions
            current_config = self._normalize_prefix(original_config)

            # For dry-run, show what would be cleaned up
            if self.dry_run:
                self.print_status("Parsing SSH config...", None, 2)
                parsed = self._parse_ssh_config(current_config)

                # Count environments and hosts
                total_hosts = sum(
                    len([line for line in env_data['lines'] if line.startswith('Host ') and '*' not in line])
                    for env_data in parsed['environments'].values()
                )

                self.print_status(f"[DRY RUN] Would reorganize {len(parsed['environments'])} environments", None, 2)
                self.print_status(f"[DRY RUN] Would reorganize {total_hosts} host entries", None, 2)
                if parsed['other']:
                    self.print_status(
                        f"[DRY RUN] Would preserve {len(parsed['other'])} unmanaged entries as-is", None, 2
                    )
                return True

            # Parse existing config
            self.print_status("Parsing SSH config...", None, 2)
            parsed = self._parse_ssh_config(current_config)

            # Optimize ProxyCommand in environment patterns to remove redundant flags
            for env_name in parsed['environments']:
                # Get existing environment lines
                env_lines = parsed['environments'][env_name]['lines']

                # Find and rebuild the ProxyCommand line to remove unnecessary default flags
                new_lines = []
                for line in env_lines:
                    if line.strip().startswith('ProxyCommand'):
                        new_lines.append(f"    ProxyCommand {self._rebuild_proxy_command(line)}")
                    else:
                        new_lines.append(line)

                parsed['environments'][env_name]['lines'] = new_lines

            # Reorganize with proper structure
            self.print_status("Reorganizing configuration...", None, 2)
            organized_config = self._organize_ssh_config(
                parsed['global'] or self._build_generic_config(),
                parsed['environments'],
                parsed['other'],
                parsed['preamble']
            )

            # This is a full rewrite, so keep a copy of what was there before
            backup_file = self.ssh_config_file.with_suffix('.bak')
            backup_file.write_text(original_config)
            if platform.system() != 'Windows':
                backup_file.chmod(0o600)
            self.print_status(f"Backed up previous config to {format_path(str(backup_file))}", True, 2)

            # Write completely rewritten config
            self.ssh_config_file.write_text(organized_config)

            # Set proper permissions on the config file
            if platform.system() != 'Windows':
                import stat
                self.ssh_config_file.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600 permissions

            if parsed['other']:
                self.print_status(
                    f"Preserved {len(parsed['other'])} unmanaged entries as-is", True, 2
                )
            self.print_status("Cleanup completed and config reorganized", True, 2)
            return True

        except Exception as e:
            self.print_status(f"Error during cleanup: {e!s}", False, 2)
            return False

    def resolve_environment_name(self, cloudx_env: str) -> str:
        """Match an environment name against one already in the SSH config.

        Environment names reach us from EC2 tags and from prompts, in whatever
        case they were written. ssh matches Host patterns case-sensitively, so
        reusing the case already on disk keeps a single environment section.

        Args:
            cloudx_env: Environment name as supplied by tag, flag or prompt

        Returns:
            str: The name to use for this environment
        """
        if not cloudx_env or not self.ssh_config_file.exists():
            return cloudx_env

        try:
            parsed = self._parse_ssh_config(self.ssh_config_file.read_text())
        except OSError:
            return cloudx_env

        existing = parsed['environments'].get(cloudx_env.lower())
        if not existing:
            return cloudx_env

        resolved = existing.get('name', cloudx_env)
        if resolved != cloudx_env:
            self.print_status(
                f"Using existing environment '{resolved}' (matched '{cloudx_env}')", True, 2
            )
        return resolved

    def _check_and_create_generic_config(self, current_config: str) -> tuple[bool, str]:
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
        
    @staticmethod
    def _insert_include_line(content: str, include_line: str) -> str:
        """Place an Include directive above the first Host/Match block.

        An Include appended to the end of the file would fall inside whatever
        Host block happens to be last, and would then apply only to that host.

        Args:
            content: Current content of the system SSH config
            include_line: The 'Include <path>' directive to add

        Returns:
            str: Content with the Include in place (unchanged if already there)
        """
        if include_line in content:
            return content

        lines = content.splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.lower().startswith(('host ', 'match ')):
                # Found the first Host or Match block, insert before it
                lines.insert(index, include_line)
                lines.insert(index + 1, "")  # Blank line for readability
                return "\n".join(lines) + "\n"

        # No Host blocks found, append at end with proper spacing
        if not content.strip():
            return include_line + "\n"
        return content.rstrip() + "\n\n" + include_line + "\n"

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
            self.print_status(f"Error creating control directory: {e!s}", False, 2)
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

        # Both end up in a Host line; reject anything that could change the
        # structure of the generated config
        for label, value in (("environment", cloudx_env), ("hostname", hostname)):
            if not self.validate_ssh_name(value):
                self.print_status(f"Invalid {label}: {value!r}", False, 2)
                self.print_status(
                    "Use letters, digits, dots, hyphens and underscores only, "
                    "starting with a letter or digit", None, 2
                )
                return False

        if self.dry_run:
            self.print_status("[DRY RUN] Would set up SSH configuration with three-tier approach")
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
            
            # 2. The environment tier is created by _add_host_entry below, which
            # parses and reorganizes the whole file

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
                except Exception:
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
                        system_config_path.write_text(
                            self._insert_include_line(content, include_line)
                        )
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
            # Name the entry that was actually written: an existing host keeps
            # the name it has, which is not necessarily the configured case.
            connect_name = (
                self.last_host_entry_name
                or f"{self.ssh_host_prefix}-{cloudx_env}-{hostname}"
            )
            self.print_status(f"Connect using: {format_command(f'ssh {connect_name}')}", None, 2)
            
            return True

        except Exception as e:
            self.print_status(f"{color_error('Error:', bold=True)} {e!s}", False, 2)
            return self.confirm_continue_after_error("SSH config issues")

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
            # Try to connect with a simple command that will exit immediately.
            # Output is captured, so any prompt would be invisible and would
            # simply burn the timeout: BatchMode disables password and
            # passphrase prompts, and accept-new answers the unknown-host-key
            # question that every first connection would otherwise ask.
            result = subprocess.run(
                [
                    'ssh',
                    '-o', 'BatchMode=yes',
                    '-o', 'StrictHostKeyChecking=accept-new',
                    '-o', 'ConnectTimeout=10',
                    ssh_host, 'exit 0'
                ],
                capture_output=True,
                text=True,
                timeout=30  # ProxyCommand may need to start the instance first
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
            self.print_status(f"Error checking SSH connection: {e!s}", False, 4)
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
            self.print_status("[DRY RUN] Would wait up to 5 minutes for SSH access if needed", None, 2)
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
        return self.confirm_continue_after_error("SSH access issues")

    def migrate_to_cloudx(self, target_dir: Path | None = None) -> bool:
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
            self.print_status(f"[DRY RUN] Would update paths in {target_dir}/config:", None, 2)

            # Show what would be replaced
            old_dir_name = vscode_dir.name
            new_dir_name = target_dir.name
            self.print_status(f"  - Replace /{old_dir_name}/ with /{new_dir_name}/", None, 3)
            self.print_status(f"  - Replace ~/.ssh/{old_dir_name} with ~/.ssh/{new_dir_name}", None, 3)
            self.print_status(f"  - Replace --ssh-key {old_dir_name} with --ssh-key {new_dir_name}", None, 3)

            self.print_status("[DRY RUN] Would update ~/.ssh/config to include new config path", None, 2)
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

            # Update config file content to reflect new paths
            config_file = target_dir / "config"
            if config_file.exists():
                self.print_status(f"Updating paths in {config_file}...", None, 2)
                config_content = config_file.read_text()
                original_content = config_content

                # Extract directory names
                old_dir_name = vscode_dir.name
                new_dir_name = target_dir.name

                # Replace absolute paths: /Users/.../.ssh/vscode/ -> /Users/.../.ssh/cloudX/
                expanded_vscode_path = str(vscode_dir)
                expanded_target_path = str(target_dir)
                config_content = config_content.replace(expanded_vscode_path + "/", expanded_target_path + "/")

                # Replace tilde paths: ~/.ssh/vscode -> ~/.ssh/cloudX
                config_content = config_content.replace(f"~/.ssh/{old_dir_name}", f"~/.ssh/{new_dir_name}")

                # Replace SSH key file references: ~/.ssh/vscode/vscode -> ~/.ssh/cloudX/cloudX
                config_content = config_content.replace(f"~/.ssh/{old_dir_name}/{old_dir_name}", f"~/.ssh/{new_dir_name}/{new_dir_name}")

                # Replace SSH key parameter in ProxyCommand: --ssh-key vscode -> --ssh-key cloudX
                config_content = config_content.replace(f"--ssh-key {old_dir_name}", f"--ssh-key {new_dir_name}")

                # Replace SSH dir parameter in ProxyCommand: --ssh-dir ~/.ssh/vscode -> --ssh-dir ~/.ssh/cloudX
                config_content = config_content.replace(f"--ssh-dir {expanded_vscode_path}", f"--ssh-dir {expanded_target_path}")

                # Only write if content changed
                if config_content != original_content:
                    config_file.write_text(config_content)
                    config_file.chmod(0o600)
                    self.print_status("Updated config file paths", True, 2)

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

                # Add the new include above the first Host block; appending it
                # would put the Include inside whatever block came last
                new_include = f"Include {target_dir}/config"
                system_config_path.write_text(
                    self._insert_include_line("\n".join(new_lines), new_include)
                )

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
            self.print_status(f"Migration failed: {e!s}", False, 2)
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
        
        if should_migrate and self.migrate_to_cloudx():
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
