"""Tests for the runtime paths: prerequisites, Include placement, flags.

- ``Include`` appended to the end of ~/.ssh/config lands inside whatever Host
  block happens to be last, so it applies only to that host. ``setup`` already
  inserted above the first block; ``migrate`` appended, and now shares the
  same helper.
- ``use_1password=False`` enabled 1Password, because ``isinstance(False, bool)``
  matched the "it's a bool, so it's on" branch.
- The AWS CLI and session-manager-plugin run inside the ProxyCommand, where a
  missing binary is nearly invisible; setup reports them up front.
"""

import pytest

from cloudx_proxy.setup import CloudXSetup


@pytest.fixture
def setup(tmp_path):
    return CloudXSetup(
        ssh_dir=str(tmp_path / "ssh"),
        ssh_host_prefix="cloudx",
        non_interactive=True,
    )


class TestIncludePlacement:
    def test_include_goes_above_the_first_host_block(self, setup):
        content = """Host github.com
    User git
"""
        result = setup._insert_include_line(content, "Include ~/.ssh/cloudX/config")

        lines = [line for line in result.splitlines() if line.strip()]
        assert lines[0] == "Include ~/.ssh/cloudX/config"
        assert lines[1] == "Host github.com"

    def test_include_goes_above_the_first_match_block(self, setup):
        content = """Match host *.internal
    ForwardAgent yes
"""
        result = setup._insert_include_line(content, "Include ~/.ssh/cloudX/config")

        lines = [line for line in result.splitlines() if line.strip()]
        assert lines[0] == "Include ~/.ssh/cloudX/config"

    def test_include_is_appended_when_there_are_no_blocks(self, setup):
        content = "ServerAliveInterval 60\n"

        result = setup._insert_include_line(content, "Include ~/.ssh/cloudX/config")

        assert result.startswith("ServerAliveInterval 60")
        assert result.rstrip().endswith("Include ~/.ssh/cloudX/config")

    def test_existing_include_is_left_alone(self, setup):
        content = "Include ~/.ssh/cloudX/config\n\nHost github.com\n    User git\n"

        result = setup._insert_include_line(content, "Include ~/.ssh/cloudX/config")

        assert result == content
        assert result.count("Include") == 1

    def test_empty_config_gets_just_the_include(self, setup):
        assert setup._insert_include_line("", "Include x") == "Include x\n"

    def test_lowercase_host_keyword_is_recognised(self, setup):
        """SSH keywords are case-insensitive, so 'host' opens a block too."""
        result = setup._insert_include_line("host github.com\n    User git\n", "Include x")

        lines = [line for line in result.splitlines() if line.strip()]
        assert lines[0] == "Include x"


class TestMigrateIncludePlacement:
    def test_migrate_does_not_bury_the_include_in_a_host_block(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / ".ssh" / "vscode").mkdir(parents=True)
        (home / ".ssh" / "vscode" / "config").write_text(
            "Host cloudx-dev-web1\n    HostName i-0123456789abcdef0\n"
        )
        (home / ".ssh" / "config").write_text(
            "Include " + str(home / ".ssh" / "vscode" / "config") + "\n\n"
            "Host github.com\n    User git\n"
        )

        setup = CloudXSetup(ssh_dir=str(home / ".ssh" / "cloudX"))
        monkeypatch.setattr(setup, "home_dir", str(home))

        assert setup.migrate_to_cloudx(home / ".ssh" / "cloudX") is True

        result = (home / ".ssh" / "config").read_text()
        lines = [line for line in result.splitlines() if line.strip()]
        include_index = next(
            i for i, line in enumerate(lines) if line.startswith("Include ")
        )
        host_index = next(
            i for i, line in enumerate(lines) if line.startswith("Host ")
        )
        assert include_index < host_index, "Include must not sit inside a Host block"
        assert "cloudX/config" in result
        assert "vscode/config" not in result


class TestOnePasswordFlag:
    def test_false_disables_1password(self, tmp_path):
        setup = CloudXSetup(ssh_dir=str(tmp_path), use_1password=False)

        assert setup.use_1password is False
        assert setup.op_vault is None

    def test_none_disables_1password(self, tmp_path):
        setup = CloudXSetup(ssh_dir=str(tmp_path), use_1password=None)

        assert setup.use_1password is False

    def test_true_enables_the_default_vault(self, tmp_path):
        setup = CloudXSetup(ssh_dir=str(tmp_path), use_1password=True)

        assert setup.use_1password is True
        assert setup.op_vault == "Private"

    def test_string_true_enables_the_default_vault(self, tmp_path):
        setup = CloudXSetup(ssh_dir=str(tmp_path), use_1password="true")

        assert setup.use_1password is True
        assert setup.op_vault == "Private"

    def test_vault_name_is_used(self, tmp_path):
        setup = CloudXSetup(ssh_dir=str(tmp_path), use_1password="Work")

        assert setup.use_1password is True
        assert setup.op_vault == "Work"


class TestPrerequisites:
    def test_reports_missing_tools(self, setup, monkeypatch, capsys):
        import cloudx_proxy.setup as setup_mod

        monkeypatch.setattr(setup_mod.shutil, "which", lambda name: None)

        assert setup.check_prerequisites() is False

        output = capsys.readouterr().out
        assert "session-manager-plugin" in output
        assert "session-manager-working-with-install-plugin" in output

    def test_passes_when_tools_are_present(self, setup, monkeypatch):
        import cloudx_proxy.setup as setup_mod

        monkeypatch.setattr(setup_mod.shutil, "which", lambda name: f"/usr/bin/{name}")

        assert setup.check_prerequisites() is True

    def test_dry_run_does_not_probe(self, tmp_path, monkeypatch):
        import cloudx_proxy.setup as setup_mod

        def fail(name):
            raise AssertionError("dry run must not probe PATH")

        monkeypatch.setattr(setup_mod.shutil, "which", fail)
        setup = CloudXSetup(ssh_dir=str(tmp_path), dry_run=True)

        assert setup.check_prerequisites() is True


class TestSshProbeIsNonInteractive:
    def test_batch_mode_and_host_key_options_are_passed(self, setup, monkeypatch):
        import cloudx_proxy.setup as setup_mod

        captured = {}

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return Result()

        monkeypatch.setattr(setup_mod.subprocess, "run", fake_run)

        assert setup.check_instance_setup("i-0123456789abcdef0", "web1", "dev") is True

        cmd = captured["cmd"]
        assert "BatchMode=yes" in cmd
        assert "StrictHostKeyChecking=accept-new" in cmd
        assert cmd[-2:] == ["cloudx-dev-web1", "exit"]
        assert captured["kwargs"]["timeout"] > 0
