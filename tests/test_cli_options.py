"""Tests locking the three-way behaviour of --1password.

The option was implemented with a custom Option subclass that assigned Click
internals after construction (`_flag_needs_value`, `_flag_default`). One of
those - `_flag_default` - is referenced nowhere in Click 8.4, so it was already
writing to an attribute nothing reads, and `flag_value`'s default changed from
None to an UNSET sentinel in the meantime. Click supports this natively via
`is_flag=False, flag_value=...`; these tests pin the behaviour so a Click
upgrade that changes it fails here rather than in the field.
"""

import pytest
from click.testing import CliRunner

from cloudx_proxy.cli import cli


def run_setup(tmp_path, monkeypatch, extra_args):
    """Invoke `setup --dry-run` with no AWS access, returning the result."""
    monkeypatch.setattr("cloudx_proxy.setup.boto3.Session", lambda *a, **k: None)

    return CliRunner().invoke(cli, ["setup", "--dry-run", "--yes", "--instance", "i-0123456789abcdef0", "--hostname", "web1", "--environment", "dev", "--ssh-config", str(tmp_path / "cloudX" / "config"), *extra_args])


class TestOpVaultOption:
    def test_omitted_means_no_op(self, tmp_path, monkeypatch):
        result = run_setup(tmp_path, monkeypatch, [])

        assert result.exit_code == 0, result.output
        assert "1Password" not in result.output
        assert "Would create SSH key pair" in result.output

    def test_bare_flag_uses_the_private_vault(self, tmp_path, monkeypatch):
        result = run_setup(tmp_path, monkeypatch, ["--1password"])

        assert result.exit_code == 0, result.output
        assert "vault: Private" in result.output

    def test_explicit_vault_is_used(self, tmp_path, monkeypatch):
        result = run_setup(tmp_path, monkeypatch, ["--1password", "Work"])

        assert result.exit_code == 0, result.output
        assert "vault: Work" in result.output

    def test_bare_flag_does_not_swallow_the_next_option(self, tmp_path, monkeypatch):
        """`--1password --instance x` must not read '--instance' as the vault."""
        monkeypatch.setattr("cloudx_proxy.setup.boto3.Session", lambda *a, **k: None)

        result = CliRunner().invoke(cli, [
            "setup", "--dry-run", "--yes",
            "--1password",
            "--instance", "i-0123456789abcdef0",
            "--hostname", "web1",
            "--environment", "dev",
            "--ssh-config", str(tmp_path / "cloudX" / "config"),
        ])

        assert result.exit_code == 0, result.output
        assert "vault: Private" in result.output
        assert "cloudx-dev-web1" in result.output

    def test_help_shows_the_optional_value(self, tmp_path):
        result = CliRunner().invoke(cli, ["setup", "--help"])

        assert result.exit_code == 0
        assert "--1password [VAULT]" in result.output


class TestListShowsThePreferredSpelling:
    """A pattern has no owner; a host does.

    cloudX is the product's name - the X is ten, after Cloud9 - so patterns are
    shown that way whichever command name was typed. A configured host keeps
    the case its owner gave it and is listed under that name.
    """

    CONFIG = """# SSH Configuration - Managed by cloudX-proxy v0.17.3

Host cloudX-* cloudx-*
    User ec2-user
    IdentitiesOnly yes

Host cloudX-DTA-* cloudx-DTA-*
    IdentityFile ~/.ssh/cloudX/cloudX
    ProxyCommand uvx cloudX-proxy connect %h %p

Host cloudX-DTA-unified
    HostName i-095f07267c26a685c

Host cloudx-DTA-lower
    HostName i-0aaaaaaaaaaaaaaaa

Host cloudx-empty-* cloudX-empty-*
    IdentityFile ~/.ssh/cloudX/cloudX
    ProxyCommand uvx cloudx-proxy connect %h %p
"""

    def run(self, tmp_path, monkeypatch, argv0, extra_args=()):
        ssh_dir = tmp_path / "cloudX"
        ssh_dir.mkdir(parents=True, exist_ok=True)
        config = ssh_dir / "config"
        config.write_text(self.CONFIG)
        monkeypatch.setattr("cloudx_proxy.cli.sys.argv", [argv0])

        return CliRunner().invoke(
            cli, ["list", "--ssh-config", str(config), *extra_args]
        )

    @pytest.mark.parametrize("argv0", ["cloudX-proxy", "cloudx-proxy"])
    def test_patterns_use_the_x_spelling_either_way(self, tmp_path, monkeypatch, argv0):
        result = self.run(tmp_path, monkeypatch, argv0, ["--detailed"])

        assert result.exit_code == 0, result.output
        assert "cloudX-*" in result.output
        assert "cloudX-DTA-*" in result.output
        assert "cloudx-DTA-*" not in result.output

    @pytest.mark.parametrize("argv0", ["cloudX-proxy", "cloudx-proxy"])
    def test_hosts_keep_their_own_case(self, tmp_path, monkeypatch, argv0):
        result = self.run(tmp_path, monkeypatch, argv0)

        assert "cloudx-DTA-lower" in result.output
        assert "cloudX-DTA-unified" in result.output
        # ...and are still shortened against either spelling
        assert "lower (" in result.output
        assert "unified (" in result.output

    def test_an_environment_without_hosts_is_not_listed(self, tmp_path, monkeypatch):
        result = self.run(tmp_path, monkeypatch, "cloudX-proxy", ["--detailed"])

        assert "Environment: DTA" in result.output
        assert "Environment: empty" not in result.output
        # It is still visible as a pattern, in the preferred spelling.
        assert "cloudX-empty-*" in result.output
