import os
import sys
import re
from pathlib import Path
import click
from . import __version__
from .core import CloudXProxy
from .setup import CloudXSetup

@click.group()
@click.version_option(version=__version__)
def cli():
    """cloudx-proxy - SSH proxy to connect VSCode Remote SSH to EC2 instances using SSM.

This tool enables seamless SSH connections from VSCode to EC2 instances using AWS Systems Manager,
eliminating the need for direct SSH access or public IP addresses.

\b
Main commands:
\b
  setup     - Configure AWS profile, SSH keys, and SSH configuration
  connect   - Connect to an EC2 instance via SSM
  list      - List configured SSH hosts"""
    pass

@cli.command()
@click.argument('instance_id')
@click.argument('port', type=int, default=22)
@click.option('--profile', default='vscode', help='AWS profile to use (default: vscode)')
@click.option('--region', help='AWS region (default: from profile, or eu-west-1 if not set)')
@click.option('--ssh-key', default='vscode', help='SSH key name to use (default: vscode)')
@click.option('--ssh-config', help='SSH config file to use (default: ~/.ssh/vscode/config)')
@click.option('--aws-env', help='AWS environment directory (default: ~/.aws, use name of directory in ~/.aws/aws-envs/)')
def connect(instance_id: str, port: int, profile: str, region: str, ssh_key: str, ssh_config: str, aws_env: str):
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
        client = CloudXProxy(
            instance_id=instance_id,
            port=port,
            profile=profile,
            region=region,
            ssh_key=ssh_key,
            ssh_config=ssh_config,
            aws_env=aws_env
        )
        
        client.log(f"cloudx-proxy@{__version__} Connecting to instance {instance_id} on port {port}...")
        
        if not client.connect():
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

@cli.command()
@click.option('--profile', default='vscode', help='AWS profile to use (default: vscode)')
@click.option('--ssh-key', default='vscode', help='SSH key name to use (default: vscode)')
@click.option('--ssh-config', help='SSH config file to use (default: ~/.ssh/vscode/config)')
@click.option('--aws-env', help='AWS environment directory (default: ~/.aws, use name of directory in ~/.aws/aws-envs/)')
@click.option('--1password', 'use_1password', default=None, help='Use 1Password SSH agent for SSH authentication. Optionally specify vault name (default: "Private")')
@click.option('--instance', help='EC2 instance ID to set up connection for')
@click.option('--hostname', help='Hostname to use for SSH configuration')
@click.option('--yes', 'non_interactive', is_flag=True, help='Non-interactive mode, use default values for all prompts')
def setup(profile: str, ssh_key: str, ssh_config: str, aws_env: str, use_1password: str, 
          instance: str, hostname: str, non_interactive: bool):
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
        setup = CloudXSetup(
            profile=profile, 
            ssh_key=ssh_key, 
            ssh_config=ssh_config, 
            aws_env=aws_env,
            use_1password=use_1password,
            instance_id=instance,
            non_interactive=non_interactive
        )
        
        print("\n\033[1;95m=== cloudx-proxy Setup ===\033[0m\n")
        
        # Set up AWS profile
        if not setup.setup_aws_profile():
            sys.exit(1)
        
        # Set up SSH key
        if not setup.setup_ssh_key():
            sys.exit(1)
        
        # Get environment and instance details
        cloudx_env = setup.prompt("Enter environment", getattr(setup, 'default_env', None))
        
        # Use the --instance parameter if provided, otherwise prompt
        instance_id = instance or setup.prompt("Enter EC2 instance ID (e.g., i-0123456789abcdef0)")
        
        # Use --hostname if provided, otherwise generate default based on instance ID in non-interactive mode
        if hostname:
            # If hostname is explicitly provided, use it directly
            setup.print_status(f"Using provided hostname: {hostname}", True, 2)
        else:
            # Generate default hostname based on instance ID for non-interactive mode
            hostname_default = f"instance-{instance_id[-7:]}" if non_interactive else None
            hostname = setup.prompt("Enter hostname for the instance", hostname_default)
        
        # Set up SSH config
        if not setup.setup_ssh_config(cloudx_env, instance_id, hostname):
            sys.exit(1)
        
        # Check instance setup status
        if not setup.wait_for_setup_completion(instance_id, hostname, cloudx_env):
            sys.exit(1)
        
    except Exception as e:
        print(f"\n\033[91mError: {str(e)}\033[0m", file=sys.stderr)
        sys.exit(1)

@cli.command()
@click.option('--ssh-config', help='SSH config file to use (default: ~/.ssh/vscode/config)')
@click.option('--environment', help='Filter hosts by environment (e.g., dev, prod)')
@click.option('--detailed', is_flag=True, help='Show detailed information including instance IDs')
def list(ssh_config: str, environment: str, detailed: bool):
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
            config_file = Path(os.path.expanduser("~/.ssh/vscode/config"))
        
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
        print(f"\n\033[1;95m=== cloudx-proxy Configured Hosts ===\033[0m\n")
        
        # Print generic patterns if any and detailed mode
        if generic_hosts and detailed:
            print("\033[1;94mGeneric Patterns:\033[0m")
            for hostname, instance_id in generic_hosts:
                print(f"  {hostname}")
            print()
            
        # Print environments and hosts
        for env, hosts in sorted(environments.items()):
            print(f"\033[1;94mEnvironment: {env}\033[0m")
            for hostname, name, instance_id in sorted(hosts, key=lambda x: x[1]):
                if detailed:
                    print(f"  {name} \033[90m({hostname})\033[0m -> \033[93m{instance_id}\033[0m")
                else:
                    print(f"  {name} \033[90m({hostname})\033[0m")
            print()
            
        # Print usage hint
        print("\033[1;93mUsage:\033[0m")
        print("  Connect with SSH:  \033[96mssh <hostname>\033[0m")
        print("  Connect with VSCode: Use Remote Explorer in VSCode")
        
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    cli()
