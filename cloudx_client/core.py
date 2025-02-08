import os
import sys
import time
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

class CloudXClient:
    def __init__(self, instance_id: str, port: int = 22, profile: str = "vscode", 
                 region: str = None, public_key_path: str = None, aws_env: str = None):
        """Initialize CloudX client for SSH tunneling via AWS SSM.
        
        Args:
            instance_id: EC2 instance ID to connect to
            port: SSH port number (default: 22)
            profile: AWS profile to use (default: "vscode")
            region: AWS region (default: from profile)
            public_key_path: Path to SSH public key (default: ~/.ssh/vscode/vscode.pub)
            aws_env: AWS environment directory (default: None, uses ~/.aws)
        """
        self.instance_id = instance_id
        self.port = port
        self.profile = profile
        
        # Configure AWS environment
        if aws_env:
            aws_env_dir = os.path.expanduser(f"~/.aws/aws-envs/{aws_env}")
            os.environ["AWS_CONFIG_FILE"] = os.path.join(aws_env_dir, "config")
            os.environ["AWS_SHARED_CREDENTIALS_FILE"] = os.path.join(aws_env_dir, "credentials")
        
        # Set up AWS session with eu-west-1 as default region
        if not region:
            # Try to get region from profile first
            session = boto3.Session(profile_name=profile)
            region = session.region_name or 'eu-west-1'
        
        self.session = boto3.Session(profile_name=profile, region_name=region)
        self.ssm = self.session.client('ssm')
        self.ec2 = self.session.client('ec2')
        self.ec2_connect = self.session.client('ec2-instance-connect')
        
        # Default public key path if not provided
        if not public_key_path:
            public_key_path = os.path.expanduser("~/.ssh/vscode/vscode.pub")
        self.public_key_path = Path(public_key_path)

    def log(self, message: str) -> None:
        """Log message to stderr to avoid interfering with SSH connection."""
        print(message, file=sys.stderr)

    def get_instance_status(self) -> str:
        """Check if instance is online in SSM."""
        try:
            response = self.ssm.describe_instance_information(
                Filters=[{'Key': 'InstanceIds', 'Values': [self.instance_id]}]
            )
            if response['InstanceInformationList']:
                return response['InstanceInformationList'][0]['PingStatus']
            return 'Offline'
        except ClientError:
            return 'Offline'

    def start_instance(self) -> bool:
        """Start the EC2 instance if it's stopped."""
        try:
            self.ec2.start_instances(InstanceIds=[self.instance_id])
            return True
        except ClientError as e:
            self.log(f"Error starting instance: {e}")
            return False

    def wait_for_instance(self, max_attempts: int = 30, delay: int = 3) -> bool:
        """Wait for instance to come online.
        
        Args:
            max_attempts: Maximum number of status checks
            delay: Seconds between checks
        
        Returns:
            bool: True if instance came online, False if timeout
        """
        for _ in range(max_attempts):
            if self.get_instance_status() == 'Online':
                return True
            time.sleep(delay)
        return False

    def push_ssh_key(self) -> bool:
        """Push SSH public key to instance via EC2 Instance Connect."""
        try:
            with open(self.public_key_path) as f:
                public_key = f.read()
            
            self.ec2_connect.send_ssh_public_key(
                InstanceId=self.instance_id,
                InstanceOSUser='ec2-user',
                SSHPublicKey=public_key
            )
            return True
        except (ClientError, FileNotFoundError) as e:
            self.log(f"Error pushing SSH key: {e}")
            return False

    def start_session(self) -> None:
        """Start SSM session with SSH port forwarding.
        
        Uses AWS CLI directly to ensure proper stdin/stdout handling for SSH ProxyCommand.
        The session manager plugin will automatically handle the data transfer.
        """
        import subprocess
        import platform
        
        try:
            # Build environment with AWS credentials configuration
            env = os.environ.copy()
            if 'AWS_CONFIG_FILE' in os.environ:
                env['AWS_CONFIG_FILE'] = os.environ['AWS_CONFIG_FILE']
            if 'AWS_SHARED_CREDENTIALS_FILE' in os.environ:
                env['AWS_SHARED_CREDENTIALS_FILE'] = os.environ['AWS_SHARED_CREDENTIALS_FILE']
            
            # Determine AWS CLI command based on platform
            aws_cmd = 'aws.exe' if platform.system() == 'Windows' else 'aws'
            
            # Use AWS CLI to start session, which properly handles stdin/stdout
            # shell=True on Windows to ensure proper PATH resolution
            if platform.system() == 'Windows':
                cmd = f'{aws_cmd} ssm start-session --target {self.instance_id} --document-name AWS-StartSSHSession --parameters portNumber={self.port} --profile {self.profile} --region {self.session.region_name}'
                subprocess.run(cmd, env=env, check=True, shell=True)
            else:
                subprocess.run([
                    aws_cmd, 'ssm', 'start-session',
                    '--target', self.instance_id,
                    '--document-name', 'AWS-StartSSHSession',
                    '--parameters', f'portNumber={self.port}',
                    '--profile', self.profile,
                    '--region', self.session.region_name
                ], env=env, check=True)
        except subprocess.CalledProcessError as e:
            self.log(f"Error starting session: {e}")
            raise

    def connect(self) -> bool:
        """Main connection flow:
        1. Check instance status
        2. Start if needed and wait for online
        3. Push SSH key
        4. Start SSM session
        """
        status = self.get_instance_status()
        
        if status != 'Online':
            self.log(f"Instance {self.instance_id} is {status}, starting...")
            if not self.start_instance():
                return False
            
            self.log("Waiting for instance to come online...")
            if not self.wait_for_instance():
                self.log("Instance failed to come online")
                return False
        
        self.log("Pushing SSH public key...")
        if not self.push_ssh_key():
            return False
        
        self.log("Starting SSM session...")
        self.start_session()
        return True
