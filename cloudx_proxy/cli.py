import os
import sys
import click
from . import __version__
from .core import CloudXProxy
from .setup import CloudXSetup

@click.group()
@click.version_option(version=__version__)
def cli():
    """cloudx-proxy - SSH proxy to connect VSCode Remote SSH to EC2 instances using SSM."""
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
    
    Example usage:
        cloudx-proxy i-0123456789abcdef0 22
        cloudx-proxy i-0123456789abcdef0 22 --profile myprofile --region eu-west-1
        cloudx-proxy i-0123456789abcdef0 22 --aws-env prod
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
def setup(profile: str, ssh_key: str, ssh_config: str, aws_env: str):
    """Set up AWS profile, SSH keys, and configuration for CloudX.
    
    This command will:
    1. Set up AWS profile with credentials
    2. Create or use existing SSH key
    3. Configure SSH for CloudX instances
    4. Check instance setup status
    
    Example usage:
        cloudx-proxy setup
        cloudx-proxy setup --profile myprofile --ssh-key mykey
        cloudx-proxy setup --ssh-config ~/.ssh/cloudx/config
    """
    try:
        setup = CloudXSetup(profile=profile, ssh_key=ssh_key, ssh_config=ssh_config, aws_env=aws_env)
        
        print("\n\033[1;95m=== cloudx-proxy Setup ===\033[0m\n")
        
        # Set up AWS profile
        if not setup.setup_aws_profile():
            sys.exit(1)
        
        # Set up SSH key
        if not setup.setup_ssh_key():
            sys.exit(1)
        
        # Get environment and instance details
        cloudx_env = setup.prompt("Enter environment", getattr(setup, 'default_env', None))
        instance_id = setup.prompt("Enter EC2 instance ID (e.g., i-0123456789abcdef0)")
        hostname = setup.prompt("Enter hostname for the instance")
        
        # Set up SSH config
        if not setup.setup_ssh_config(cloudx_env, instance_id, hostname):
            sys.exit(1)
        
        # Check instance setup status
        if not setup.wait_for_setup_completion(instance_id, hostname, cloudx_env):
            sys.exit(1)
        
    except Exception as e:
        print(f"\n\033[91mError: {str(e)}\033[0m", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    cli()
