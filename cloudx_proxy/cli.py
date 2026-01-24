import os
import sys
import re
from pathlib import Path
import click
from . import __version__
from .core import CloudXProxy
from .setup import CloudXSetup
from .colors import header, success, error as color_error, info, format_instance_id, format_hostname, format_command, secondary


class OptionalValueOption(click.Option):
    """Click option that allows an optional value (e.g., --flag or --flag value)."""

    def __init__(self, *args, **kwargs):
        _flag_value = kwargs.pop("flag_value", None)
        if _flag_value is None:
            raise ValueError("flag_value is required for OptionalValueOption")
        if kwargs.get('nargs', 1) != 1:
            raise ValueError("OptionalValueOption only supports nargs=1")

        # Force Click to treat this as a regular option (so it can take a value)
        kwargs.setdefault('is_flag', False)
        kwargs['flag_value'] = _flag_value

        super().__init__(*args, **kwargs)

        # Ensure Click knows this flag may omit its value and fall back to flag_value
        self._flag_needs_value = True
        self.flag_value = _flag_value
        self._flag_default = _flag_value




@click.group()
@click.version_option(version=__version__)
def cli():
    """cloudx-proxy - SSH proxy to connect VSCode Remote SSH to EC2 instances using SSM.

This tool enables seamless SSH connections from VSCode to EC2 instances (see https://github.com/easytocloud/cloudX) using AWS Systems Manager,
eliminating the need for direct SSH access or public IP addresses.

\b
Main commands:
\b
  setup     - Configure AWS profile, SSH keys, and SSH configuration
  connect   - Connect to an EC2 instance via SSM
  list      - List configured SSH hosts
  migrate   - Migrate from legacy vscode directory to cloudX"""
    pass

@cli.command()
@click.argument('instance_id')
@click.argument('port', type=int, default=22)
@click.option('--profile', default='vscode', help='AWS profile to use (default: vscode)')
@click.option('--region', help='AWS region (default: from profile, or eu-west-1 if not set)')
@click.option('--ssh-key', default='vscode', help='SSH key name to use (default: vscode)')
@click.option('--ssh-config', help='SSH config file to use (default: ~/.ssh/vscode/config)')
@click.option('--ssh-dir', help='Directory for SSH keys and config')
@click.option('--aws-env', help='AWS environment directory (default: ~/.aws, use name of directory in ~/.aws/aws-envs/)')
@click.option('--dry-run', is_flag=True, help='Preview connection workflow without executing')
def connect(instance_id: str, port: int, profile: str, region: str, ssh_key: str, ssh_config: str, ssh_dir: str, aws_env: str, dry_run: bool):
    """Connect to an EC2 instance via SSM.

    INSTANCE_ID is the EC2 instance ID to connect to (e.g., i-0123456789abcdef0)

    \b
    Example usage:
    \b
    cloudx-proxy connect i-0123456789abcdef0 22
    cloudx-proxy connect i-0123456789abcdef0 22 --profile myprofile --region eu-west-1
    cloudx-proxy connect i-0123456789abcdef0 22 --ssh-config ~/.ssh/cloudx/config
    cloudx-proxy connect i-0123456789abcdef0 22 --aws-env prod
    """
    try:
        # Validate instance ID format
        if not CloudXSetup.validate_instance_id(instance_id):
            print(color_error(f"Error: Invalid EC2 instance ID format: {instance_id}"), file=sys.stderr)
            print("Instance IDs must start with 'i-' followed by 8 or 17 hexadecimal characters", file=sys.stderr)
            print("Examples: i-1234567890abcdef0 or i-12345678", file=sys.stderr)
            sys.exit(1)

        client = CloudXProxy(
            instance_id=instance_id,
            port=port,
            profile=profile,
            region=region,
            ssh_key=ssh_key,
            ssh_config=ssh_config,
            ssh_dir=ssh_dir,
            aws_env=aws_env,
            dry_run=dry_run
        )
        
        client.log(f"cloudx-proxy@{__version__} Connecting to instance {instance_id} on port {port}...")
        
        if not client.connect():
            sys.exit(1)
            
    except Exception as e:
        print(color_error(f"Error: {str(e)}"), file=sys.stderr)
        sys.exit(1)

@cli.command()
@click.option('--profile', default='cloudX', help='AWS profile to use (default: cloudX)')
@click.option('--ssh-key', default='cloudX', help='SSH key name to use (default: cloudX)')
@click.option('--ssh-config', help='SSH config file to use (default: ~/.ssh/cloudX/config)')
@click.option('--ssh-dir', help='Directory for SSH keys and config (default: ~/.ssh/cloudX)')
@click.option('--aws-env', help='AWS environment directory (default: ~/.aws, use name of directory in ~/.aws/aws-envs/)')
@click.option(
    '--1password',
    'use_1password',
    cls=OptionalValueOption,
    flag_value='Private',
    default=None,
    metavar='[VAULT]',
    help='Use 1Password SSH agent for SSH authentication. Without a value the "Private" vault is used; optionally specify a vault name.'
)
@click.option('--instance', help='EC2 instance ID to set up connection for')
@click.option('--hostname', help='Hostname to use for SSH configuration')
@click.option('--ssh-host-prefix', help='Prefix for SSH hosts (default: cloudx or cloudX depending on command name)')
@click.option('--yes', 'non_interactive', is_flag=True, help='Non-interactive mode, use default values for all prompts')
@click.option('--dry-run', is_flag=True, help='Preview setup changes without executing')
def setup(profile: str, ssh_key: str, ssh_config: str, ssh_dir: str, aws_env: str, use_1password: str,
          instance: str, hostname: str, ssh_host_prefix: str, non_interactive: bool, dry_run: bool):
    """Set up AWS profile, SSH keys, and configuration for CloudX.
    
    \b
    This command will:
    \b
    1. Set up AWS profile with credentials
    2. Create or use existing SSH key
    3. Configure SSH for CloudX instances
    4. Check instance setup status
    
    \b
    Example usage:
    \b
    cloudx-proxy setup
    cloudx-proxy setup --profile myprofile --ssh-key mykey
    cloudx-proxy setup --ssh-config ~/.ssh/cloudx/config
    cloudx-proxy setup --1password
    cloudx-proxy setup --1password Work
    cloudx-proxy setup --instance i-0123456789abcdef0 --hostname myserver --yes
    """
    try:
        # Determine default prefix based on command name if not provided
        if not ssh_host_prefix:
            cmd_name = os.path.basename(sys.argv[0])
            if cmd_name == 'cloudX-proxy':
                ssh_host_prefix = 'cloudX'
            else:
                ssh_host_prefix = 'cloudx'

        setup = CloudXSetup(
            profile=profile,
            ssh_key=ssh_key,
            ssh_config=ssh_config,
            ssh_dir=ssh_dir,
            aws_env=aws_env,
            use_1password=use_1password,
            instance_id=instance,
            ssh_host_prefix=ssh_host_prefix,
            non_interactive=non_interactive,
            dry_run=dry_run
        )
        
        if dry_run:
            print(f"\n{header(f'=== {ssh_host_prefix}-proxy Setup (DRY RUN) ===')}\n")
        else:
            print(f"\n{header(f'=== {ssh_host_prefix}-proxy Setup ===')}\n")
        
        # Check for migration
        setup.check_and_perform_migration()
        
        # Set up AWS profile
        if not setup.setup_aws_profile():
            sys.exit(1)
        
        # Set up SSH key
        if not setup.setup_ssh_key():
            sys.exit(1)
        
        # Get instance ID first, then fetch tags to auto-populate environment and hostname
        instance_id = instance or setup.prompt("Enter EC2 instance ID (e.g., i-0123456789abcdef0)")

        # Validate instance ID format
        if not CloudXSetup.validate_instance_id(instance_id):
            setup.print_status(
                f"Invalid EC2 instance ID format: {instance_id}",
                False,
                2
            )
            setup.print_status(
                "Instance IDs must start with 'i-' followed by 8 or 17 hexadecimal characters",
                None,
                2
            )
            setup.print_status(
                "Examples: i-1234567890abcdef0 or i-12345678",
                None,
                2
            )
            sys.exit(1)

        # Fetch instance tags to get environment and hostname defaults
        setup.print_status("Fetching instance tags...", None, 2)
        tag_env, tag_hostname = setup.get_instance_tags(instance_id)

        # Use environment from tag, fall back to AWS user default, or prompt
        env_default = tag_env or getattr(setup, 'default_env', None)
        cloudx_env = setup.prompt("Enter environment", env_default)

        # Use --hostname if provided, otherwise use tag-based default
        if hostname:
            # If hostname is explicitly provided, use it directly
            setup.print_status(f"Using provided hostname: {hostname}", True, 2)
        else:
            # Use hostname from tag, or generate default based on instance ID for non-interactive mode
            hostname_default = tag_hostname or (f"instance-{instance_id[-7:]}" if non_interactive else None)
            hostname = setup.prompt("Enter hostname for the instance", hostname_default)
        
        # Set up SSH config
        if not setup.setup_ssh_config(cloudx_env, instance_id, hostname):
            sys.exit(1)
        
        # Check instance setup status
        if not setup.wait_for_setup_completion(instance_id, hostname, cloudx_env):
            sys.exit(1)
        
    except Exception as e:
        print(f"\n{color_error(f'Error: {str(e)}')}", file=sys.stderr)
        sys.exit(1)

@cli.command()
@click.option('--ssh-config', help='SSH config file to use (default: ~/.ssh/cloudX/config)')
@click.option('--environment', help='Filter hosts by environment (e.g., dev, prod)')
@click.option('--detailed', is_flag=True, help='Show detailed information including instance IDs')
@click.option('--dry-run', is_flag=True, help='Preview list output format')
def list(ssh_config: str, environment: str, detailed: bool, dry_run: bool):
    """List configured cloudx-proxy SSH hosts.
    
    This command parses the SSH configuration file and displays all configured cloudx-proxy hosts.
    Hosts are grouped by environment for easier navigation.
    
    \b
    Example usage:
    \b
    cloudx-proxy list
    cloudx-proxy list --environment dev
    cloudx-proxy list --ssh-config ~/.ssh/cloudx/config
    cloudx-proxy list --detailed
    """
    try:
        # Determine SSH config file path
        if ssh_config:
            config_file = Path(os.path.expanduser(ssh_config))
        else:
            # Check for cloudX config first, then vscode
            cloudx_config = Path(os.path.expanduser("~/.ssh/cloudX/config"))
            vscode_config = Path(os.path.expanduser("~/.ssh/vscode/config"))
            
            if cloudx_config.exists():
                config_file = cloudx_config
            elif vscode_config.exists():
                config_file = vscode_config
            else:
                config_file = cloudx_config
        
        if dry_run:
            print(f"\n\033[1;95m=== cloudx-proxy List (DRY RUN) ===\033[0m\n")
            print(f"[DRY RUN] Would read SSH config from: {config_file}")
            if environment:
                print(f"[DRY RUN] Would filter hosts by environment: {environment}")
            if detailed:
                print(f"[DRY RUN] Would show detailed information including instance IDs")
            print(f"[DRY RUN] Would parse SSH configuration and display grouped hosts")
            return
        
        if not config_file.exists():
            print(f"SSH config file not found: {config_file}")
            print("Run 'cloudx-proxy setup' to create a configuration.")
            sys.exit(1)
        
        # Read SSH config file
        config_content = config_file.read_text()
        
        # Parse hosts using regex
        # Match Host entries for cloudx hosts (case-insensitive)
        host_pattern = r'Host\s+(cloud[xX]-[^\s]+)(?:\s*\n(?:(?!\s*Host\s+).)*?(?i:hostname)\s+([^\s]+))?'
        hosts = re.finditer(host_pattern, config_content, re.DOTALL)
        
        # Group hosts by environment
        environments = {}
        generic_hosts = []
        
        for match in hosts:
            hostname = match.group(1)
            instance_id = match.group(2) if match.group(2) else "N/A"
            
            # Skip generic patterns like cloudx-* or cloudx-dev-*
            if hostname.endswith('*'):
                generic_hosts.append((hostname, instance_id))
                continue
                
            # Extract environment from hostname (format: cloudx-{env}-{name})
            parts = hostname.split('-')
            if len(parts) >= 3:
                env = parts[1]
                name = '-'.join(parts[2:])
                
                # Filter by environment if specified
                if environment and env != environment:
                    continue
                    
                if env not in environments:
                    environments[env] = []
                    
                environments[env].append((hostname, name, instance_id))
        
        # Display results
        if not environments and not generic_hosts:
            print("No cloudx-proxy hosts configured.")
            print("Run 'cloudx-proxy setup' to configure a host.")
            return
            
        # Print header
        print(f"\n{header('=== cloudx-proxy Configured Hosts ===')}\n")

        # Print generic patterns if any and detailed mode
        if generic_hosts and detailed:
            print(info("Generic Patterns:"))
            for hostname, instance_id in generic_hosts:
                print(f"  {format_hostname(hostname)}")
            print()

        # Print environments and hosts
        for env, hosts in sorted(environments.items()):
            print(info(f"Environment: {env}"))
            for hostname, name, instance_id in sorted(hosts, key=lambda x: x[1]):
                if detailed:
                    print(f"  {name} {secondary(f'({hostname})')} → {format_instance_id(instance_id)}")
                else:
                    print(f"  {name} {secondary(f'({hostname})')}")
            print()

        # Print usage hint
        print(info("Usage:"))
        print(f"  Connect with SSH:  {format_command('ssh <hostname>')}")
        print("  Connect with VSCode: Use Remote Explorer in VSCode")
        
    except Exception as e:
        print(color_error(f"Error: {str(e)}"), file=sys.stderr)
        sys.exit(1)

@cli.command()
@click.option('--target-dir', help='Target directory for migration (default: ~/.ssh/cloudX)')
@click.option('--dry-run', is_flag=True, help='Preview migration without executing')
def migrate(target_dir: str, dry_run: bool):
    """Migrate from legacy vscode directory to cloudX.
    
    This command moves the configuration from ~/.ssh/vscode to ~/.ssh/cloudX
    (or another specified directory) and updates ~/.ssh/config.
    """
    try:
        setup = CloudXSetup(dry_run=dry_run)
        
        target_path = Path(os.path.expanduser(target_dir)) if target_dir else None
        
        if setup.migrate_to_cloudx(target_path):
            print("\n\033[92mMigration completed successfully!\033[0m")
        else:
            sys.exit(1)
            
    except Exception as e:
        print(color_error(f"Error: {str(e)}"), file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    cli()
