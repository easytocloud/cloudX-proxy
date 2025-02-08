import os
import sys
import click
from .core import CloudXClient

@click.command()
@click.argument('instance_id')
@click.argument('port', type=int, default=22)
@click.option('--profile', default='vscode', help='AWS profile to use (default: vscode)')
@click.option('--region', help='AWS region (default: from profile, or eu-west-1 if not set)')
@click.option('--key-path', help='Path to SSH public key (default: ~/.ssh/vscode/vscode.pub)')
@click.option('--aws-env', help='AWS environment directory (default: ~/.aws, use name of directory in ~/.aws/aws-envs/)')
def main(instance_id: str, port: int, profile: str, region: str, key_path: str, aws_env: str):
    """CloudX Client - Connect to EC2 instances via SSM for VSCode Remote SSH.
    
    INSTANCE_ID is the EC2 instance ID to connect to (e.g., i-0123456789abcdef0)
    
    Example usage:
        uvx cloudx-client i-0123456789abcdef0 22
        uvx cloudx-client i-0123456789abcdef0 22 --profile myprofile --region eu-west-1
        uvx cloudx-client i-0123456789abcdef0 22 --aws-env prod
    """
    try:
        client = CloudXClient(
            instance_id=instance_id,
            port=port,
            profile=profile,
            region=region,
            public_key_path=key_path,
            aws_env=aws_env
        )
        
        if not client.connect():
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
