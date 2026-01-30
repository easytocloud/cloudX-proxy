# SSH Configuration Structure

cloudX-proxy generates a hierarchical three-tier SSH configuration that maps to the cloudX infrastructure concepts. Understanding this structure is essential for troubleshooting and extending configurations.

## Overview

The SSH config uses SSH's pattern matching to create an inheritance-like structure:

```
┌─────────────────────────────────────────────────────────────┐
│  Global: Host cloudX-*                                      │
│  (applies to ALL cloudX hosts)                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Environment: Host cloudX-{env}-*                   │    │
│  │  (applies to all hosts in a specific environment)   │    │
│  │  ┌─────────────────────────────────────────────┐    │    │
│  │  │  Host: Host cloudX-{env}-{hostname}         │    │    │
│  │  │  (maps to a specific EC2 instance)          │    │    │
│  │  └─────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Tier 1: Global Configuration (`Host cloudX-*`)

The global tier defines settings that apply to **all cloudX hosts**, regardless of environment.

**Pattern**: `cloudX-*`

**Purpose**: Set common SSH behavior for all cloudX connections.

**Typical settings**:
```ssh-config
Host cloudX-*
    User ec2-user
    TCPKeepAlive yes
    ControlMaster auto
    ControlPath ~/.ssh/control/%r@%h:%p
    ControlPersist 4h
```

**Settings explained**:
- `User ec2-user`: All cloudX instances use the ec2-user account
- `TCPKeepAlive yes`: Prevents connection drops during idle periods
- `ControlMaster auto`: Enables SSH multiplexing for connection reuse
- `ControlPath`: Socket location for multiplexed connections
- `ControlPersist 4h`: Keep master connection open for 4 hours

**Note**: On Windows, `Control*` directives are commented out as the default Windows SSH client doesn't support them.

## Tier 2: Environment Configuration (`Host cloudX-{env}-*`)

The environment tier defines settings specific to a **cloudX environment**. CloudX instances are tagged with an `Environment` tag (e.g., `dev`, `prod`, `lab`) that determines which environment configuration applies.

**Pattern**: `cloudX-{env}-*` (e.g., `cloudX-dev-*`, `cloudX-Prod-*`)

**Purpose**: Configure authentication and proxy settings for all instances in an environment.

**Typical settings**:
```ssh-config
Host cloudX-Prod-*
    IdentityFile ~/.ssh/cloudX/mykey
    IdentitiesOnly yes
    ProxyCommand uvx cloudX-proxy connect %h %p --profile myprofile --ssh-key mykey --ssh-dir ~/.ssh/cloudX
```

**Settings explained**:
- `IdentityFile`: Path to the SSH private key for this environment
- `IdentitiesOnly yes`: Only use the specified key, don't try others from ssh-agent
- `ProxyCommand`: The cloudX-proxy connect command that:
  - Checks if the instance is running (starts it if needed)
  - Pushes the SSH public key to the instance
  - Establishes the SSM tunnel

**Why per-environment?**
- Different environments may use different AWS profiles (credentials)
- Different environments may use different SSH keys
- The `--profile` in ProxyCommand determines which AWS credentials are used

## Tier 3: Host Configuration (`Host cloudX-{env}-{hostname}`)

The host tier maps a **friendly hostname** to a specific **EC2 instance ID**.

**Pattern**: `cloudX-{env}-{hostname}` (e.g., `cloudX-Prod-foobar`)

**Purpose**: Provide the instance ID that cloudX-proxy needs to connect.

**Typical settings**:
```ssh-config
Host cloudX-Prod-foobar
    HostName i-0123456789abcdef0
```

**Settings explained**:
- `HostName`: The EC2 instance ID (not a DNS hostname!)
  - This value is passed to cloudX-proxy via `%h` in the ProxyCommand
  - cloudX-proxy uses this instance ID to check status, start, and connect

**How the hostname is derived**:
- During `cloudX-proxy setup`, the instance's tags are read
- The `Environment` tag determines the environment part
- The `Name` tag (or user-specified hostname) determines the hostname part

## Configuration Inheritance

SSH applies configurations from most specific to least specific. When connecting to `cloudX-Prod-foobar`:

1. **Host cloudX-Prod-foobar** matches first → sets `HostName`
2. **Host cloudX-Prod-*** matches next → sets `IdentityFile`, `IdentitiesOnly`, `ProxyCommand`
3. **Host cloudX-*** matches last → sets `User`, `TCPKeepAlive`, `Control*`

The result is a fully configured connection with all necessary settings.

## Example: Complete Configuration

For a user with instances in two environments:

```ssh-config
# Tier 1: Global (all cloudX hosts)
Host cloudX-*
    User ec2-user
    TCPKeepAlive yes
    ControlMaster auto
    ControlPath ~/.ssh/control/%r@%h:%p
    ControlPersist 4h

# Tier 2: Environment - Development
Host cloudX-dev-*
    IdentityFile ~/.ssh/cloudX/devkey
    IdentitiesOnly yes
    ProxyCommand uvx cloudX-proxy connect %h %p --profile cloudX-dev --ssh-key devkey --ssh-dir ~/.ssh/cloudX

# Tier 2: Environment - Production
Host cloudX-Prod-*
    IdentityFile ~/.ssh/cloudX/prodkey
    IdentitiesOnly yes
    ProxyCommand uvx cloudX-proxy connect %h %p --profile cloudX-prod --ssh-key prodkey --ssh-dir ~/.ssh/cloudX

# Tier 3: Individual hosts
Host cloudX-dev-myworkstation
    HostName i-0123456789abcdef0

Host cloudX-dev-testserver
    HostName i-0fedcba9876543210

Host cloudX-Prod-foobar
    HostName i-0abcdef1234567890
```

## Relationship to CloudX Infrastructure

| SSH Config Tier | CloudX Concept | AWS Resource |
|-----------------|----------------|--------------|
| Global (`cloudX-*`) | cloudX system-wide defaults | N/A |
| Environment (`cloudX-{env}-*`) | cloudX-environment stack | IAM group, VPC subnet, security group |
| Host (`cloudX-{env}-{hostname}`) | cloudX-instance stack | EC2 instance |

## Adding New Instances

When running `cloudX-proxy setup` for a new instance:

1. **If the environment exists**: Only a new Tier 3 (host) entry is added
2. **If the environment is new**: Both Tier 2 (environment) and Tier 3 (host) entries are added
3. **Tier 1 is created once**: The global config is only created on first setup

This design means adding instances to an existing environment is minimal - just one line mapping hostname to instance ID.

## File Manipulation Rules

When reading, parsing, or modifying the SSH config file, follow these rules strictly:

### Reading and Parsing

1. **Always read the entire file** before making any modifications
2. **Parse into tiers**: Identify and separate entries into Tier 1, Tier 2, and Tier 3 based on their host patterns
3. **Ignore comments** during parsing, with one exception (see below)
4. **Preserve Tier 3 inline comments**: Comments on the same line as a Tier 3 `Host` directive must be preserved
   ```ssh-config
   Host cloudX-dev-mine # t3.small
   ```
   The `# t3.small` comment survives all read/write cycles as it contains useful instance metadata.

### Modifying

1. **Prevent duplicates**: Before adding any entry, check if it already exists
   - For Tier 1: Check if `Host cloudX-*` exists
   - For Tier 2: Check if `Host cloudX-{env}-*` exists for the specific environment
   - For Tier 3: Check if `Host cloudX-{env}-{hostname}` exists
2. **Update in place**: If an entry exists, update its settings rather than creating a duplicate
3. **Associate Tier 3 with Tier 2**: Keep track of which Tier 3 hosts belong to which environment

### Writing

Always write the config file in this specific order:

```
Tier 1 (Global)
├── Tier 2 (Environment A)
│   ├── Tier 3 (Host A1)
│   ├── Tier 3 (Host A2)
│   └── ...
├── Tier 2 (Environment B)
│   ├── Tier 3 (Host B1)
│   └── ...
└── ...
```

**Output format**:

```ssh-config
# =============================================================================
# cloudX Global Configuration
# =============================================================================
Host cloudX-*
    User ec2-user
    TCPKeepAlive yes
    ...

# =============================================================================
# Environment: dev
# =============================================================================
Host cloudX-dev-*
    IdentityFile ~/.ssh/cloudX/devkey
    IdentitiesOnly yes
    ProxyCommand uvx cloudX-proxy connect %h %p --profile cloudX-dev --ssh-key devkey

Host cloudX-dev-myworkstation # t3.medium
    HostName i-0123456789abcdef0

Host cloudX-dev-testserver # t3.small
    HostName i-0fedcba9876543210

# =============================================================================
# Environment: Prod
# =============================================================================
Host cloudX-Prod-*
    IdentityFile ~/.ssh/cloudX/prodkey
    IdentitiesOnly yes
    ProxyCommand uvx cloudX-proxy connect %h %p --profile cloudX-prod --ssh-key prodkey

Host cloudX-Prod-foobar # m5.large
    HostName i-0abcdef1234567890
```

### Comment Handling Summary

| Comment Type | Example | Behavior |
|--------------|---------|----------|
| Standalone comment lines | `# This is a comment` | Ignored/discarded on rewrite |
| Tier 2 header comments | `# Environment: dev` | Regenerated on write |
| Tier 3 inline comments | `Host cloudX-dev-mine # t3.small` | **Preserved** |
| Setting comments | `IdentityFile ~/.ssh/key # my key` | Ignored/discarded |

### Pseudocode for Config Manipulation

```python
def manipulate_ssh_config(config_path, new_entries):
    # 1. Read entire file
    content = read_file(config_path)

    # 2. Parse into tiers
    tier1 = parse_tier1(content)  # Host cloudX-*
    tier2_map = parse_tier2(content)  # {env: config}
    tier3_map = parse_tier3(content)  # {env: [{host, instance_id, comment}]}

    # 3. Apply modifications (check for duplicates first)
    for entry in new_entries:
        if is_duplicate(entry, tier1, tier2_map, tier3_map):
            update_existing(entry, ...)
        else:
            add_new(entry, ...)

    # 4. Write in correct order
    output = []
    output.append(format_tier1(tier1))

    for env in sorted(tier2_map.keys()):
        output.append(format_tier2_header(env))
        output.append(format_tier2(tier2_map[env]))

        for host in tier3_map.get(env, []):
            output.append(format_tier3(host))  # Preserves inline comment

    write_file(config_path, output)
```
