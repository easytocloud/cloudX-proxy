"""Existing installations must keep working untouched.

`uvx cloudX-proxy` resolves to the latest release every time it runs, so an
existing user's SSH config - written by an earlier version and never edited
again - is handed straight to this code. Nothing here may require them to
change a file or re-run setup.

The fixtures below are literal output from v0.17.1, with the ssh directory
templated so they can be materialised under tmp_path.
"""

import shlex

import pytest
from click.testing import CliRunner

from cloudx_proxy.cli import cli
from cloudx_proxy.setup import CloudXSetup

# --- Configs as v0.17.1 wrote them -----------------------------------------

V017_SINGLE_HOST = """# SSH Configuration - Managed by cloudx-proxy v0.17.1

# ==============================================================================
#  GLOBAL
# ==============================================================================

Host cloudx-*
    User ec2-user
    TCPKeepAlive yes
    IdentitiesOnly yes
    ControlMaster auto
    ControlPath ~/.ssh/control/%r@%h:%p
    ControlPersist 4h

# ==============================================================================
#  dev
# ==============================================================================

Host cloudx-dev-*
    IdentityFile {ssh_dir}/cloudX
    ProxyCommand uvx cloudx-proxy connect %h %p --ssh-config {ssh_dir}/config

Host cloudx-dev-web1
    HostName i-0123456789abcdef0
"""

V017_MULTI_HOST = """# SSH Configuration - Managed by cloudx-proxy v0.17.1

# ==============================================================================
#  GLOBAL
# ==============================================================================

Host cloudx-*
    User ec2-user
    TCPKeepAlive yes
    IdentitiesOnly yes
    ControlMaster auto
    ControlPath ~/.ssh/control/%r@%h:%p
    ControlPersist 4h

# ==============================================================================
#  dev
# ==============================================================================

Host cloudx-dev-*
    IdentityFile {ssh_dir}/cloudX
    ProxyCommand uvx cloudx-proxy connect %h %p --ssh-config {ssh_dir}/config

Host cloudx-dev-web1
    HostName i-0123456789abcdef0

Host cloudx-dev-web2
    HostName i-1111111111111111a

# ==============================================================================
#  prod
# ==============================================================================

Host cloudx-prod-*
    IdentityFile {ssh_dir}/cloudX
    ProxyCommand uvx cloudx-proxy connect %h %p --ssh-config {ssh_dir}/config

Host cloudx-prod-db1
    HostName i-2222222222222222b
"""

V017_ONEPASSWORD = """# SSH Configuration - Managed by cloudx-proxy v0.17.1

# ==============================================================================
#  GLOBAL
# ==============================================================================

Host cloudx-*
    User ec2-user
    TCPKeepAlive yes
    IdentitiesOnly yes
    ControlMaster auto
    ControlPath ~/.ssh/control/%r@%h:%p
    ControlPersist 4h

# ==============================================================================
#  dev
# ==============================================================================

Host cloudx-dev-*
    IdentityAgent ~/.1password/agent.sock
    IdentityFile {ssh_dir}/cloudX.pub
    ProxyCommand uvx cloudx-proxy connect %h %p --ssh-config {ssh_dir}/config

Host cloudx-dev-web1
    HostName i-0123456789abcdef0
"""

V017_AWS_ENV = """# SSH Configuration - Managed by cloudx-proxy v0.17.1

# ==============================================================================
#  GLOBAL
# ==============================================================================

Host cloudx-*
    User ec2-user
    TCPKeepAlive yes
    IdentitiesOnly yes
    ControlMaster auto
    ControlPath ~/.ssh/control/%r@%h:%p
    ControlPersist 4h

# ==============================================================================
#  dev
# ==============================================================================

Host cloudx-dev-*
    IdentityFile {ssh_dir}/cloudX
    ProxyCommand uvx cloudx-proxy connect %h %p --aws-env acme --ssh-config {ssh_dir}/config

Host cloudx-dev-web1
    HostName i-0123456789abcdef0
"""

V017_UPPERCASE = """# SSH Configuration - Managed by cloudX-proxy v0.17.1

# ==============================================================================
#  GLOBAL
# ==============================================================================

Host cloudX-*
    User ec2-user
    TCPKeepAlive yes
    IdentitiesOnly yes
    ControlMaster auto
    ControlPath ~/.ssh/control/%r@%h:%p
    ControlPersist 4h

# ==============================================================================
#  dev
# ==============================================================================

Host cloudX-dev-*
    IdentityFile {ssh_dir}/cloudX
    ProxyCommand uvx cloudX-proxy connect %h %p --ssh-config {ssh_dir}/config

Host cloudX-dev-web1
    HostName i-0123456789abcdef0
"""

FIXTURES = {
    "single_host": (V017_SINGLE_HOST, {"ssh_host_prefix": "cloudx"}),
    "multi_host": (V017_MULTI_HOST, {"ssh_host_prefix": "cloudx"}),
    "onepassword": (V017_ONEPASSWORD, {"ssh_host_prefix": "cloudx", "op_vault": "Private"}),
    "aws_env": (V017_AWS_ENV, {"ssh_host_prefix": "cloudx", "aws_env": "acme"}),
    "uppercase": (V017_UPPERCASE, {"ssh_host_prefix": "cloudX"}),
}


def materialise(tmp_path, template, kwargs):
    """Write a v0.17.1 config into tmp_path and return (setup, content)."""
    ssh_dir = tmp_path / "cloudX"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    content = template.format(ssh_dir=ssh_dir)
    (ssh_dir / "config").write_text(content)
    setup = CloudXSetup(ssh_dir=str(ssh_dir), non_interactive=True, **kwargs)
    return setup, content


def without_version_header(content):
    """Drop the managed-by header, which is restamped with the running version."""
    return [
        line for line in content.splitlines()
        if not line.startswith("# SSH Configuration - Managed by")
    ]


class TestExistingConfigsAreUnchanged:
    """cleanup rewrites the whole file; on an untouched config it must no-op."""

    @pytest.mark.parametrize("name", sorted(FIXTURES))
    def test_cleanup_changes_nothing_but_the_version_stamp(self, tmp_path, name):
        template, kwargs = FIXTURES[name]
        setup, before = materialise(tmp_path, template, kwargs)

        assert setup.cleanup_config() is True

        after = setup.ssh_config_file.read_text()
        assert without_version_header(after) == without_version_header(before), (
            f"{name}: cleanup changed an existing v0.17.1 config"
        )

    @pytest.mark.parametrize("name", sorted(FIXTURES))
    def test_only_the_version_header_line_differs(self, tmp_path, name):
        """Pin the exception: the header is restamped, nothing else may be."""
        template, kwargs = FIXTURES[name]
        setup, before = materialise(tmp_path, template, kwargs)
        setup.cleanup_config()
        after = setup.ssh_config_file.read_text()

        differing = [
            (a, b) for a, b in zip(before.splitlines(), after.splitlines(), strict=True)
            if a != b
        ]

        assert len(differing) <= 1, f"{name}: more than the header changed: {differing}"
        for old_line, new_line in differing:
            assert old_line.startswith("# SSH Configuration - Managed by")
            assert new_line.startswith("# SSH Configuration - Managed by")

    @pytest.mark.parametrize("name", sorted(FIXTURES))
    def test_a_backup_of_the_original_is_kept(self, tmp_path, name):
        template, kwargs = FIXTURES[name]
        setup, before = materialise(tmp_path, template, kwargs)

        setup.cleanup_config()

        backup = setup.ssh_config_file.with_suffix(".bak")
        assert backup.exists()
        assert backup.read_text() == before

    @pytest.mark.parametrize("name", sorted(FIXTURES))
    def test_cleanup_is_idempotent(self, tmp_path, name):
        template, kwargs = FIXTURES[name]
        setup, _ = materialise(tmp_path, template, kwargs)

        setup.cleanup_config()
        once = setup.ssh_config_file.read_text()
        setup.cleanup_config()
        assert setup.ssh_config_file.read_text() == once


class TestExistingConfigsStillParse:
    @pytest.mark.parametrize("name", sorted(FIXTURES))
    def test_hosts_and_environments_are_found(self, tmp_path, name):
        template, kwargs = FIXTURES[name]
        setup, content = materialise(tmp_path, template, kwargs)

        parsed = setup._parse_ssh_config(content)

        assert parsed["global"], f"{name}: global section lost"
        assert parsed["environments"], f"{name}: environments lost"
        assert parsed["other"] == [], f"{name}: managed content misfiled as unmanaged"

    def test_list_command_reads_a_v017_config(self, tmp_path):
        setup, _ = materialise(tmp_path, V017_MULTI_HOST, {"ssh_host_prefix": "cloudx"})

        result = CliRunner().invoke(cli, ["list", "--ssh-config", str(setup.ssh_config_file)])

        assert result.exit_code == 0, result.output
        assert "web1" in result.output
        assert "web2" in result.output
        assert "db1" in result.output
        assert "i-0123456789abcdef0" in result.output

    def test_adding_a_host_preserves_the_existing_entries(self, tmp_path):
        setup, content = materialise(tmp_path, V017_MULTI_HOST, {"ssh_host_prefix": "cloudx"})

        assert setup._add_host_entry("dev", "i-9999999999999999f", "web3", content) is True

        after = setup.ssh_config_file.read_text()
        for kept in ("cloudx-dev-web1", "cloudx-dev-web2", "cloudx-prod-db1", "cloudx-dev-web3"):
            assert f"Host {kept}" in after
        assert "i-2222222222222222b" in after, "an unrelated environment's host was disturbed"


class TestHistoricalProxyCommandsStillParse:
    """ssh runs whatever ProxyCommand is already in the user's config."""

    @pytest.mark.parametrize("command", [
        "uvx cloudx-proxy connect %h %p",
        "uvx cloudx-proxy connect %h %p --ssh-config ~/.ssh/cloudX/config",
        "uvx cloudx-proxy connect %h %p --profile vscode --ssh-key vscode",
        "uvx cloudX-proxy connect %h %p --ssh-dir ~/.ssh/vscode",
        "uvx cloudx-proxy connect %h %p --aws-env prod --region eu-central-1",
        "uvx cloudx-proxy connect %h %p --profile cloudX --ssh-key cloudX --ssh-config ~/.ssh/cloudX/config",
        "uvx cloudx-proxy connect %h %p --aws-env acme --ssh-config ~/.ssh/cloudX/config",
    ])
    def test_connect_accepts_the_command(self, command):
        args = shlex.split(command)
        args = args[args.index("connect"):]
        args = [a.replace("%h", "i-0123456789abcdef0").replace("%p", "22") for a in args]

        result = CliRunner().invoke(cli, [*args, "--dry-run"])

        assert result.exit_code == 0, f"{command} -> {result.output}{result.exception}"


class TestLegacyVscodeLayout:
    """The pre-cloudX ~/.ssh/vscode layout must keep working."""

    def test_vscode_prefixed_config_round_trips(self, tmp_path):
        ssh_dir = tmp_path / "vscode"
        ssh_dir.mkdir(parents=True)
        content = f"""Host cloudx-*
    User ec2-user
    TCPKeepAlive yes

Host cloudx-dev-*
    IdentityFile {ssh_dir}/vscode
    ProxyCommand uvx cloudx-proxy connect %h %p --profile vscode --ssh-key vscode --ssh-config {ssh_dir}/config

Host cloudx-dev-web1
    HostName i-0123456789abcdef0
"""
        (ssh_dir / "config").write_text(content)
        setup = CloudXSetup(
            ssh_dir=str(ssh_dir), ssh_host_prefix="cloudx",
            profile="vscode", ssh_key="vscode", non_interactive=True,
        )

        assert setup.cleanup_config() is True

        after = setup.ssh_config_file.read_text()
        assert "Host cloudx-dev-web1" in after
        assert "--profile vscode" in after
        assert "--ssh-key vscode" in after
        assert f"IdentityFile {ssh_dir}/vscode" in after
