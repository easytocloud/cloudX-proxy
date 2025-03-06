import os
import sys
import time
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

class CloudXProxy:
    def __init__(self, instance_id: str, port: int = 22, profile: str = "vscode", 
                 region: str = None, ssh_key: str = "vscode", ssh_config: str = None, aws_env: str = None):
        """Initialize CloudX client for SSH tunneling via AWS SSM.
        
        Args:
            instance_id: EC2 instance ID to connect to
            port: SSH port number (default: 22)
            profile: AWS profile to use (default: "vscode")
            region: AWS region (default: from profile)
            ssh_key: SSH key name to use (default: "vscode")
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
        
        # Set up SSH configuration and key paths
        if ssh_config:
            self.ssh_config_file = os.path.expanduser(ssh_config)
            self.ssh_dir = os.path.dirname(self.ssh_config_file)
        else:
            self.ssh_dir = os.path.expanduser("~/.ssh/vscode")
            self.ssh_config_file = os.path.join(self.ssh_dir, "config")
            
        self.ssh_key = os.path.join(self.ssh_dir, f"{ssh_key}.pub")

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
        """Push SSH public key to instance via EC2 Instance Connect.
        
        Determines which SSH key to use (regular key or 1Password-managed key),
        then pushes the correct public key to the instance.
        """
        try:
            # Check if file exists with .pub extension (could be a non-1Password key)
            # or if the .pub extension is already part of self.ssh_key (because of 1Password integration)
            key_path = self.ssh_key
            if not key_path.endswith('.pub'):
                key_path += '.pub'
                
            self.log(f"Using public key: {key_path}")
            
            with open(key_path) as f:
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
        
        When used as a ProxyCommand, we need to:
        1. Pass through stdin/stdout directly to AWS CLI
        2. Only use stderr for logging
        3. Let the session manager plugin handle the actual data transfer
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
            
            # Build command as list (works for both Windows and Unix)
            cmd = [
                aws_cmd, 'ssm', 'start-session',
                '--target', self.instance_id,
                '--document-name', 'AWS-StartSSHSession',
                '--parameters', f'portNumber={self.port}',
                '--profile', self.profile,
                '--region', self.session.region_name
            ]
            
            # Start AWS CLI process with direct stdin/stdout pass-through
            process = subprocess.Popen(
                cmd,
                env=env,
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=subprocess.PIPE,  # Capture stderr for our logging
                shell=platform.system() == 'Windows'  # shell=True only on Windows
            )
            
            # Monitor stderr for logging while process runs
            while True:
                err_line = process.stderr.readline()
                if not err_line and process.poll() is not None:
                    break
                if err_line:
                    self.log(err_line.decode().strip())
            
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd)
            
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
