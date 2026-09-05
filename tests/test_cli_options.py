"""Tests locking the three-way behaviour of --1password.

The option was implemented with a custom Option subclass that assigned Click
internals after construction (`_flag_needs_value`, `_flag_default`). One of
those - `_flag_default` - is referenced nowhere in Click 8.4, so it was already
writing to an attribute nothing reads, and `flag_value`'s default changed from
None to an UNSET sentinel in the meantime. Click supports this natively via
`is_flag=False, flag_value=...`; these tests pin the behaviour so a Click
upgrade that changes it fails here rather than in the field.
"""

import ntpath

import pytest
from click.testing import CliRunner

from cloudx_proxy.cli import cli, prefix_from_command_name
from cloudx_proxy.setup import CloudXSetup, plural


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


SYMBOLS = ("\u25cb", "\u2713", "\u2717")  # neutral, success, failure


def status_lines(output):
    """Every status line as (indent, symbol, text)."""
    parsed = []
    for line in output.splitlines():
        stripped = line.lstrip(" ")
        if stripped[:1] in SYMBOLS:
            parsed.append((len(line) - len(stripped), stripped[0], stripped[1:].strip()))
    return parsed


class TestOutputGrid:
    """`print_header` prepended two newlines while the banner above it appended
    one, so the first section sat under three blank lines and every section
    after it under two. Indents had drifted to 3 and to orphaned 2s and 4s.
    """

    def full_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cloudx_proxy.setup.boto3.Session", lambda *a, **k: None)
        monkeypatch.setattr("cloudx_proxy.cli.sys.argv", ["cloudX-proxy"])

        return CliRunner().invoke(cli, [
            "setup", "--dry-run", "--yes",
            "--instance", "i-0123456789abcdef0",
            "--hostname", "web1", "--environment", "dev",
            "--ssh-config", str(tmp_path / "cloudX" / "config"),
        ])

    def test_every_status_line_sits_on_the_grid(self, tmp_path, monkeypatch):
        result = self.full_run(tmp_path, monkeypatch)

        lines = status_lines(result.output)
        assert lines, result.output
        for indent, _symbol, text in lines:
            assert indent in (0, 2, 4), f"off-grid indent {indent}: {text!r}"

    def test_no_detail_is_orphaned(self, tmp_path, monkeypatch):
        """A detail belongs to a step, and a sub-detail to a detail."""
        result = self.full_run(tmp_path, monkeypatch)

        seen = set()
        for line in result.output.splitlines():
            if line.startswith("==="):
                seen.clear()  # a header starts a new section
                continue
            stripped = line.lstrip(" ")
            if stripped[:1] not in SYMBOLS:
                continue
            indent = len(line) - len(stripped)
            if indent:
                assert indent - 2 in seen, f"orphaned at indent {indent}: {stripped!r}"
            seen.add(indent)

    def test_cleanup_sits_on_the_grid_too(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cloudx_proxy.cli.sys.argv", ["cloudX-proxy"])
        ssh_dir = tmp_path / "cloudX"
        ssh_dir.mkdir(parents=True)
        (ssh_dir / "config").write_text(
            "Host cloudX-dev-*\n    IdentityFile ~/.ssh/cloudX/cloudX\n\n"
            "Host cloudX-dev-web1\n    HostName i-0123456789abcdef0\n"
        )

        result = CliRunner().invoke(
            cli, ["cleanup", "--ssh-config", str(ssh_dir / "config")]
        )

        assert result.exit_code == 0, result.output
        indents = [indent for indent, _s, _t in status_lines(result.output)]
        assert indents, result.output
        assert set(indents) <= {0, 2, 4}
        assert 0 in indents, "cleanup's details had no step above them"

    def test_sections_are_separated_by_one_blank_line(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cloudx_proxy.setup.boto3.Session", lambda *a, **k: None)
        monkeypatch.setattr("cloudx_proxy.cli.sys.argv", ["cloudX-proxy"])

        result = CliRunner().invoke(cli, [
            "setup", "--dry-run", "--yes",
            "--instance", "i-0123456789abcdef0",
            "--hostname", "web1", "--environment", "dev",
            "--ssh-config", str(tmp_path / "cloudX" / "config"),
        ])

        assert result.exit_code == 0, result.output
        assert "\n\n\n" not in result.output, "blank lines are stacking up"
        assert "=== Prerequisites ===" in result.output

    @pytest.mark.parametrize("argv0", ["cloudX-proxy", "cloudx-proxy"])
    def test_banners_use_the_product_spelling(self, tmp_path, monkeypatch, argv0):
        monkeypatch.setattr("cloudx_proxy.setup.boto3.Session", lambda *a, **k: None)
        monkeypatch.setattr("cloudx_proxy.cli.sys.argv", [argv0])

        result = CliRunner().invoke(cli, [
            "setup", "--dry-run", "--yes",
            "--instance", "i-0123456789abcdef0",
            "--hostname", "web1", "--environment", "dev",
            "--ssh-config", str(tmp_path / "cloudX" / "config"),
        ])

        assert "=== cloudX-proxy Setup (DRY RUN) ===" in result.output


class TestOneFailureOneCross:
    """A ✗ marks the outcome, not every observation on the way to it.

    The 1Password check reported "socket not found at ~/.1password/agent.sock"
    as a failure before it had looked anywhere else, so a snap install saw a ✗
    immediately followed by a ✓, and a genuine failure produced four marked
    lines for one problem.
    """

    def linux_setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cloudx_proxy.setup.platform.system", lambda: "Linux")
        setup = CloudXSetup(
            ssh_dir=str(tmp_path / "cloudX"), non_interactive=True, op_vault="Private"
        )
        setup.op_agent_sock = tmp_path / "absent.sock"
        setup.op_agent_sock_snap = tmp_path / "snap.sock"
        return setup

    def test_a_recoverable_miss_is_neutral(self, tmp_path, monkeypatch, capsys):
        setup = self.linux_setup(tmp_path, monkeypatch)
        setup.op_agent_sock_snap.write_text("")  # the snap agent is there

        assert setup._check_op_agent() is True

        marks = [symbol for _i, symbol, _t in status_lines(capsys.readouterr().out)]
        assert "✗" not in marks, "a miss we recovered from was reported as a failure"

    def test_a_real_failure_is_marked_once(self, tmp_path, monkeypatch, capsys):
        setup = self.linux_setup(tmp_path, monkeypatch)

        assert setup._check_op_agent() is False

        marks = [symbol for _i, symbol, _t in status_lines(capsys.readouterr().out)]
        assert marks.count("✗") == 1, f"one failure, one cross: {marks}"


class TestCountsAgreeWithTheirNoun:
    """`Would reorganize 1 environments` reads like a bug in the tool."""

    def cleanup_output(self, tmp_path, monkeypatch, config, args=()):
        monkeypatch.setattr("cloudx_proxy.cli.sys.argv", ["cloudX-proxy"])
        ssh_dir = tmp_path / "cloudX"
        ssh_dir.mkdir(parents=True, exist_ok=True)
        (ssh_dir / "config").write_text(config)

        result = CliRunner().invoke(
            cli, ["cleanup", "--ssh-config", str(ssh_dir / "config"), *args]
        )
        assert result.exit_code == 0, result.output
        return result.output

    ONE = """Host cloudX-dev-*
    IdentityFile ~/.ssh/cloudX/cloudX

Host cloudX-dev-web1
    HostName i-0123456789abcdef0

Host mybox
    HostName 10.0.0.1
"""

    TWO = ONE + """
Host cloudX-prd-*
    IdentityFile ~/.ssh/cloudX/cloudX

Host cloudX-prd-web1
    HostName i-0aaaaaaaaaaaaaaaa

Host cloudX-prd-web2
    HostName i-0bbbbbbbbbbbbbbbb

Host otherbox
    HostName 10.0.0.2
"""

    def test_one_of_each(self, tmp_path, monkeypatch):
        output = self.cleanup_output(tmp_path, monkeypatch, self.ONE, ["--dry-run"])

        assert "1 environment\n" in output or "1 environment " in output
        assert "1 environments" not in output
        assert "1 host entry" in output
        assert "1 unmanaged entry as-is" in output

    def test_more_than_one_of_each(self, tmp_path, monkeypatch):
        output = self.cleanup_output(tmp_path, monkeypatch, self.TWO, ["--dry-run"])

        assert "2 environments" in output
        assert "3 host entries" in output
        assert "2 unmanaged entries as-is" in output

    def test_the_real_run_agrees_too(self, tmp_path, monkeypatch):
        assert "1 unmanaged entry as-is" in self.cleanup_output(
            tmp_path, monkeypatch, self.ONE
        )
        assert "2 unmanaged entries as-is" in self.cleanup_output(
            tmp_path, monkeypatch, self.TWO
        )


class TestPluralHelper:
    def test_one(self):
        assert plural(1, "environment") == "1 environment"

    def test_zero_and_many(self):
        assert plural(0, "environment") == "0 environments"
        assert plural(7, "environment") == "7 environments"

    def test_irregular(self):
        assert plural(1, "host entry", "host entries") == "1 host entry"
        assert plural(2, "host entry", "host entries") == "2 host entries"


class TestPrefixFromCommandName:
    """On Windows a console script is an .exe.

    sys.argv[0] therefore ends in one, a bare basename never equalled
    'cloudX-proxy', and every Windows user silently got the lowercase prefix
    whichever of the two commands they typed.
    """

    def test_posix(self, monkeypatch):
        for argv0, expected in (
            ("/home/erik/.local/bin/cloudX-proxy", "cloudX"),
            ("/home/erik/.local/bin/cloudx-proxy", "cloudx"),
            ("cloudX-proxy", "cloudX"),
        ):
            monkeypatch.setattr("cloudx_proxy.cli.sys.argv", [argv0])
            assert prefix_from_command_name() == expected, argv0

    def test_windows_exe(self, monkeypatch):
        monkeypatch.setattr("cloudx_proxy.cli.os.path", ntpath)
        for argv0, expected in (
            (r"C:\Users\erik\AppData\Roaming\uv\tools\x\Scripts\cloudX-proxy.exe", "cloudX"),
            (r"C:\Users\erik\AppData\Roaming\uv\tools\x\Scripts\cloudx-proxy.exe", "cloudx"),
        ):
            monkeypatch.setattr("cloudx_proxy.cli.sys.argv", [argv0])
            assert prefix_from_command_name() == expected, argv0
