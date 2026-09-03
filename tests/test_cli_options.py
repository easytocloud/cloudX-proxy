"""Tests locking the three-way behaviour of --1password.

The option was implemented with a custom Option subclass that assigned Click
internals after construction (`_flag_needs_value`, `_flag_default`). One of
those - `_flag_default` - is referenced nowhere in Click 8.4, so it was already
writing to an attribute nothing reads, and `flag_value`'s default changed from
None to an UNSET sentinel in the meantime. Click supports this natively via
`is_flag=False, flag_value=...`; these tests pin the behaviour so a Click
upgrade that changes it fails here rather than in the field.
"""

from click.testing import CliRunner

from cloudx_proxy.cli import cli


def run_setup(tmp_path, monkeypatch, extra_args):
    """Invoke `setup --dry-run` with no AWS access, returning the result."""
    import cloudx_proxy.setup as setup_mod

    monkeypatch.setattr(setup_mod.boto3, "Session", lambda *a, **k: None)

    return CliRunner().invoke(cli, ["setup", "--dry-run", "--yes", "--instance", "i-0123456789abcdef0", "--hostname", "web1", "--environment", "dev", "--ssh-config", str(tmp_path / "cloudX" / "config"), *extra_args])


class TestOnePasswordOption:
    def test_omitted_means_no_1password(self, tmp_path, monkeypatch):
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
        import cloudx_proxy.setup as setup_mod

        monkeypatch.setattr(setup_mod.boto3, "Session", lambda *a, **k: None)

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
