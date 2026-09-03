"""Tests for what cloudx-proxy writes into the SSH configuration.

Environment names and hostnames become part of a ``Host`` line, and the
hostname default is read from an EC2 ``Name`` tag rather than typed by the
user, so a value containing whitespace used to produce two host aliases and
neither was the one the user asked for. Paths written into the ProxyCommand
had the same problem one level down: ssh runs ProxyCommand through a shell,
so an unquoted path containing a space broke the connection entirely.
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


class TestValidateSshName:
    @pytest.mark.parametrize("name", [
        "dev",
        "pre-prod",
        "web1",
        "my_host",
        "host.example",
        "Prod",
        "0abc",
    ])
    def test_valid(self, name):
        assert CloudXSetup.validate_ssh_name(name) is True

    @pytest.mark.parametrize("name", [
        "",
        None,
        "my host",          # would become two Host aliases
        "web\ttab",
        "web*",             # would widen the pattern
        "web?",
        "web#comment",      # would start an inline comment
        "-leading-hyphen",
        ".leading-dot",
        "_leading",
        "quote'name",
        'quote"name',
        "semi;colon",
        "new\nline",
    ])
    def test_invalid(self, name):
        assert CloudXSetup.validate_ssh_name(name) is False


class TestSetupSshConfigRejectsBadNames:
    def test_hostname_with_a_space_is_refused(self, setup):
        assert setup.setup_ssh_config("dev", "i-0123456789abcdef0", "my host") is False
        assert not setup.ssh_config_file.exists()

    def test_environment_with_a_space_is_refused(self, setup):
        assert setup.setup_ssh_config("my env", "i-0123456789abcdef0", "web1") is False
        assert not setup.ssh_config_file.exists()

    def test_hostname_with_a_glob_is_refused(self, setup):
        assert setup.setup_ssh_config("dev", "i-0123456789abcdef0", "web*") is False

    def test_validation_runs_before_dry_run_output(self, tmp_path):
        """A dry run must not claim it would write an invalid host either."""
        setup = CloudXSetup(
            ssh_dir=str(tmp_path / "ssh"),
            ssh_host_prefix="cloudx",
            non_interactive=True,
            dry_run=True,
        )
        assert setup.setup_ssh_config("dev", "i-0123456789abcdef0", "my host") is False


class TestQuoteShellArgument:
    @pytest.mark.parametrize("value", [
        "cloudX",
        "/home/erik/.ssh/cloudX/config",
        "pre-prod",
    ])
    def test_ordinary_values_are_untouched(self, value):
        assert CloudXSetup.quote_shell_argument(value) == value

    def test_value_with_a_space_is_quoted(self):
        quoted = CloudXSetup.quote_shell_argument("/Users/First Last/.ssh/config")
        assert quoted != "/Users/First Last/.ssh/config"
        assert quoted.startswith(("'", '"'))
        assert quoted.endswith(("'", '"'))

    def test_quoted_value_round_trips_through_a_shell(self):
        import shlex
        original = "/Users/First Last/.ssh/cloudX/config"
        assert shlex.split(CloudXSetup.quote_shell_argument(original)) == [original]


class TestProxyCommandQuoting:
    def test_config_path_with_spaces_is_quoted(self, tmp_path):
        ssh_dir = tmp_path / "My SSH Dir"
        setup = CloudXSetup(ssh_dir=str(ssh_dir), ssh_host_prefix="cloudx")

        command = setup._build_proxy_command()

        import shlex
        tokens = shlex.split(command)
        assert str(ssh_dir / "config") in tokens

    def test_aws_env_is_quoted(self, tmp_path):
        setup = CloudXSetup(
            ssh_dir=str(tmp_path / "ssh"),
            ssh_host_prefix="cloudx",
            aws_env="two words",
        )

        import shlex
        tokens = shlex.split(setup._build_proxy_command())
        assert tokens[tokens.index("--aws-env") + 1] == "two words"

    def test_cleanup_preserves_a_quoted_aws_env(self, tmp_path):
        setup = CloudXSetup(
            ssh_dir=str(tmp_path / "ssh"),
            ssh_host_prefix="cloudx",
            non_interactive=True,
        )
        setup.ssh_config_file.parent.mkdir(parents=True, exist_ok=True)
        setup.ssh_config_file.write_text("""Host cloudx-*
    User ec2-user

Host cloudx-dev-*
    ProxyCommand uvx cloudx-proxy connect %h %p --aws-env 'two words'

Host cloudx-dev-web1
    HostName i-0123456789abcdef0
""")

        assert setup.cleanup_config() is True

        result = setup.ssh_config_file.read_text()
        assert "--aws-env 'two words'" in result


class TestIdentityFileQuoting:
    """ssh_config(5) values containing spaces need double quotes of their own."""

    def test_key_path_with_spaces_is_quoted(self, tmp_path):
        ssh_dir = tmp_path / "My SSH Dir"
        setup = CloudXSetup(ssh_dir=str(ssh_dir), ssh_host_prefix="cloudx")

        auth = setup._build_auth_config()

        assert f'IdentityFile "{ssh_dir / "cloudX"}"' in auth

    def test_1password_key_path_with_spaces_is_quoted(self, tmp_path):
        ssh_dir = tmp_path / "My SSH Dir"
        setup = CloudXSetup(
            ssh_dir=str(ssh_dir), ssh_host_prefix="cloudx", use_1password="Private"
        )

        auth = setup._build_auth_config()

        assert f'IdentityFile "{ssh_dir / "cloudX"}.pub"' in auth

    def test_ordinary_key_path_is_not_quoted(self, tmp_path):
        setup = CloudXSetup(ssh_dir=str(tmp_path / "ssh"), ssh_host_prefix="cloudx")

        auth = setup._build_auth_config()

        assert f'IdentityFile {tmp_path / "ssh" / "cloudX"}' in auth
        assert '"' not in auth
