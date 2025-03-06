import os
import json
import subprocess
from pathlib import Path

def check_1password_cli() -> tuple:
    """Check if 1Password CLI is installed and authenticated.
    
    Returns:
        tuple: (installed: bool, authenticated: bool, version: str)
    """
    try:
        # Check if 1Password CLI is installed
        result = subprocess.run(
            ['op', '--version'],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            return False, False, ""
            
        version = result.stdout.strip()
        
        # Check if 1Password CLI is authenticated
        result = subprocess.run(
            ['op', 'account', 'list'],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            return True, False, version
            
        return True, True, version
        
    except FileNotFoundError:
        return False, False, ""
    except Exception:
        return False, False, ""

def check_ssh_agent(agent_sock_path: str) -> bool:
    """Check if 1Password SSH agent is running.
    
    Args:
        agent_sock_path: Path to the SSH agent socket
        
    Returns:
        bool: True if agent is running
    """
    try:
        # Check if the socket file exists
        if not os.path.exists(agent_sock_path):
            return False
            
        # Check if agent is active
        env = os.environ.copy()
        env['SSH_AUTH_SOCK'] = agent_sock_path
        
        result = subprocess.run(
            ['ssh-add', '-l'],
            env=env,
            capture_output=True,
            text=True,
            check=False
        )
        
        if "Could not open a connection to your authentication agent" in result.stderr:
            return False
            
        return True
        
    except Exception:
        return False

def list_ssh_keys() -> list:
    """List SSH keys stored in 1Password.
    
    Returns:
        list: List of SSH key items
    """
    try:
        # List SSH keys in 1Password using the correct command - confusingly, the category is "SSH Key" where the OUTPUT show "SSH_KEY"
        result = subprocess.run(
            ['op', 'item', 'list', '--categories', 'SSH Key', '--format=json'],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            return []
            
        items = json.loads(result.stdout)
        return items
        
    except Exception:
        return []

def create_ssh_key(title: str, vault: str) -> tuple:
    """Create a new SSH key in 1Password.
    
    Args:
        title: Title for the SSH key
        vault: Vault ID to store the key in
        
    Returns:
        tuple: (success: bool, public_key: str, item_id: str)
    """
    try:
        # Create a new SSH key in 1Password
        result = subprocess.run(
            [
                'op', 'item', 'create',
                '--category=ssh-key', # and yet a different way to specify the category
                f'--title={title}',
                f'--vault={vault}'
            ],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            return False, "", ""
            
        # Parse the output to extract the public key and item ID
        output_lines = result.stdout.strip().split('\n')
        item_id = ""
        public_key = ""
        
        for idx, line in enumerate(output_lines):
            if line.startswith("ID:"):
                item_id = line.split(":", 1)[1].strip()
            
            # Check for "public key:" in the line
            if "public key:" in line.lower():
                public_key = line.split(":", 1)[1].strip()
                
        # If we got the item ID but not the public key, try to get it separately
        if item_id and not public_key:
            result = subprocess.run(
                ['op', 'item', 'get', item_id, '--fields', 'public key'],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                public_key = result.stdout.strip()
        
        return item_id and public_key, public_key, item_id
        
    except Exception:
        return False, "", ""

def get_vaults() -> list:
    """Get list of available 1Password vaults.
    
    Returns:
        list: List of vault objects with 'id' and 'name' keys
    """
    try:
        result = subprocess.run(
            ['op', 'vault', 'list', '--format=json'],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            return []
            
        vaults = json.loads(result.stdout)
        return vaults
        
    except Exception:
        return []

def save_public_key(public_key: str, key_path: str) -> bool:
    """Save the public key to a file with proper permissions.
    
    Args:
        public_key: The public key content
        key_path: Path to save the public key
        
    Returns:
        bool: True if successful
    """
    try:
        # Create parent directories if needed
        os.makedirs(os.path.dirname(key_path), exist_ok=True)
        
        # Write the public key
        with open(key_path, 'w') as f:
            f.write(public_key)
            
        # Set permissions (644) on Unix-like systems
        if os.name != 'nt':  # Not Windows
            import stat
            os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IROTH | stat.S_IRGRP)
            
        return True
        
    except Exception:
        return False
