"""Tests that --yes and --dry-run report what actually happened.

Recovery prompts default to "yes". ``prompt`` returns the default in
non-interactive mode, so every "Would you like to continue anyway?" handler
answered itself and returned True: setup exited 0 having written nothing,
which is the worst possible outcome for a provisioning pipeline.

``--dry-run`` called ``describe_instances`` to read the Name tag, so a preview
needed live AWS credentials, and ``--dry-run --yes`` could not run at all.
"""

import pytest
from click.testing import CliRunner

from cloudx_proxy.cli import cli
from cloudx_proxy.setup import CloudXSetup


@pytest.fixture
def blocked_setup(tmp_path):
    """A setup whose config file cannot be written: its parent is a file."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    return CloudXSetup(
        ssh_config=str(blocker / "config"),
        ssh_host_prefix="cloudx",
        non_interactive=True,
    )


class TestFailuresAreNotReportedAsSuccess:
    def test_ssh_config_failure_returns_false(self, blocked_setup):
        result = blocked_setup.setup_ssh_config("dev", "i-0123456789abcdef0", "web1")

        assert result is False, "a failure must not be reported as success under --yes"
        assert not blocked_setup.ssh_config_file.exists()

    def test_ssh_key_failure_returns_false(self, blocked_setup, monkeypatch):
        def boom(*args, **kwargs):
            raise OSError("cannot generate a key here")

        monkeypatch.setattr("cloudx_proxy.setup.subprocess.run", boom)

        assert blocked_setup.setup_ssh_key() is False

    def test_add_host_entry_failure_returns_false(self, blocked_setup):
        assert blocked_setup._add_host_entry("dev", "i-0123456789abcdef0", "web1", "") is False

    def test_unreachable_instance_returns_false(self, tmp_path, monkeypatch):
        setup = CloudXSetup(
            ssh_dir=str(tmp_path / "ssh"),
            ssh_host_prefix="cloudx",
            non_interactive=True,
        )
        monkeypatch.setattr(setup, "check_instance_setup", lambda *a: False)
        monkeypatch.setattr("cloudx_proxy.setup.time.sleep", lambda seconds: None)
        monkeypatch.setattr(setup, "prompt", lambda message, default=None: default)

        assert setup.wait_for_setup_completion("i-0123456789abcdef0", "web1", "dev") is False


class TestConfirmContinueAfterError:
    def test_non_interactive_refuses(self, tmp_path):
        setup = CloudXSetup(ssh_dir=str(tmp_path), non_interactive=True)

        assert setup.confirm_continue_after_error("test failure") is False

    def test_interactive_default_continues(self, tmp_path, monkeypatch):
        setup = CloudXSetup(ssh_dir=str(tmp_path), non_interactive=False)
        monkeypatch.setattr("builtins.input", lambda prompt="": "")

        assert setup.confirm_continue_after_error("test failure") is True

    def test_interactive_no_aborts(self, tmp_path, monkeypatch):
        setup = CloudXSetup(ssh_dir=str(tmp_path), non_interactive=False)
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")

        assert setup.confirm_continue_after_error("test failure") is False


class TestOpIsNotSilentlySubstituted:
    def test_unavailable_op_fails_under_yes(self, tmp_path, monkeypatch):
        setup = CloudXSetup(
            ssh_dir=str(tmp_path / "ssh"),
            op_vault="Private",
            non_interactive=True,
        )
        monkeypatch.setattr(setup, "_check_op_availability", lambda: False)

        assert setup.setup_ssh_key() is False, (
            "must not quietly fall back to an on-disk key when 1Password was asked for"
        )
        assert setup.op_enabled is True, "the request must not be rewritten"


class TestDryRunDoesNotCallAws:
    def test_get_instance_tags_makes_no_aws_call(self, tmp_path, monkeypatch):
        def fail(*args, **kwargs):
            raise AssertionError("dry run must not create a boto3 session")

        monkeypatch.setattr("cloudx_proxy.setup.boto3.Session", fail)
        setup = CloudXSetup(ssh_dir=str(tmp_path / "ssh"), dry_run=True)

        assert setup.get_instance_tags("i-0123456789abcdef0") == (None, None)

    def test_full_dry_run_setup_needs_no_credentials(self, tmp_path, monkeypatch):
        def fail(*args, **kwargs):
            raise AssertionError("dry run must not create a boto3 session")

        monkeypatch.setattr("cloudx_proxy.setup.boto3.Session", fail)

        result = CliRunner().invoke(cli, [
            "setup", "--dry-run", "--yes",
            "--instance", "i-0123456789abcdef0",
            "--hostname", "web1",
            "--environment", "dev",
            "--ssh-config", str(tmp_path / "cloudX" / "config"),
        ])

        assert result.exit_code == 0, result.output
        assert "cloudx-dev-web1" in result.output
        assert not (tmp_path / "cloudX").exists(), "dry run must not write anything"

    def test_missing_environment_is_reported_not_guessed(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cloudx_proxy.setup.boto3.Session", lambda *a, **k: None)

        result = CliRunner().invoke(cli, [
            "setup", "--dry-run", "--yes",
            "--instance", "i-0123456789abcdef0",
            "--hostname", "web1",
            "--ssh-config", str(tmp_path / "cloudX" / "config"),
        ])

        assert result.exit_code == 1
        assert "Could not determine the environment" in result.output
        assert "--environment" in result.output


class TestEnvironmentOption:
    def test_explicit_environment_is_used(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cloudx_proxy.setup.boto3.Session", lambda *a, **k: None)

        result = CliRunner().invoke(cli, [
            "setup", "--dry-run", "--yes",
            "--instance", "i-0123456789abcdef0",
            "--hostname", "web1",
            "--environment", "pre-prod",
            "--ssh-config", str(tmp_path / "cloudX" / "config"),
        ])

        assert result.exit_code == 0, result.output
        assert "cloudx-pre-prod-*" in result.output

    def test_invalid_environment_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cloudx_proxy.setup.boto3.Session", lambda *a, **k: None)

        result = CliRunner().invoke(cli, [
            "setup", "--dry-run", "--yes",
            "--instance", "i-0123456789abcdef0",
            "--hostname", "web1",
            "--environment", "bad env",
            "--ssh-config", str(tmp_path / "cloudX" / "config"),
        ])

        assert result.exit_code == 1
        assert "Invalid environment" in result.output
