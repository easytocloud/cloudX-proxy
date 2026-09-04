"""Regression tests for SSH config parsing and rewriting.

These cover three data-loss defects in ``_parse_ssh_config`` /
``_organize_ssh_config``, all of which corrupted or discarded configuration
during the full rewrite performed by ``cleanup`` and ``_add_host_entry``:

1. Entries cloudx-proxy does not manage (``Host github.com``, ``Match`` blocks)
   were silently dropped. ``setup`` supports pointing ``--ssh-config`` at
   ``~/.ssh/config`` itself, so this could wipe a user's entire SSH config.
2. Environment names containing a hyphen (``pre-prod``) did not match the
   ``(\\w+)`` pattern, so the environment block - identity and ProxyCommand
   included - was deleted while its hosts were refiled under a truncated
   environment name.
3. Environment lookups were case-sensitive on one side only, so an environment
   arriving as ``Dev`` (EC2 ``Name`` tags preserve case) produced a second
   section beside an existing ``dev`` one.
"""

import pytest

from cloudx_proxy.setup import CloudXSetup


@pytest.fixture
def setup(tmp_path):
    """A CloudXSetup writing to an isolated ssh dir."""
    return CloudXSetup(
        ssh_dir=str(tmp_path / "ssh"),
        ssh_host_prefix="cloudx",
        non_interactive=True,
    )


def write_config(setup, content):
    """Seed the setup's config file and return its content."""
    setup.ssh_config_file.parent.mkdir(parents=True, exist_ok=True)
    setup.ssh_config_file.write_text(content)
    return content


def host_names(content):
    """Every Host/Match section header in a config, in order."""
    return [
        line.strip()
        for line in content.splitlines()
        if line.strip().lower().startswith(("host ", "match "))
    ]


MANAGED = """Host cloudx-*
    User ec2-user

Host cloudx-dev-*
    IdentityFile ~/.ssh/cloudX/cloudX
    ProxyCommand uvx cloudx-proxy connect %h %p

Host cloudx-dev-web1
    HostName i-0123456789abcdef0
"""


class TestUnmanagedEntriesArePreserved:
    """Defect 1: a full rewrite must never drop what it does not understand."""

    def test_foreign_hosts_survive_cleanup(self, setup):
        write_config(setup, """Host github.com
    User git
    IdentityFile ~/.ssh/id_ed25519

""" + MANAGED + """
Host bastion
    HostName 10.0.0.1
""")

        assert setup.cleanup_config() is True

        result = setup.ssh_config_file.read_text()
        assert "Host github.com" in result
        assert "IdentityFile ~/.ssh/id_ed25519" in result
        assert "Host bastion" in result
        assert "HostName 10.0.0.1" in result

    def test_match_blocks_survive_cleanup(self, setup):
        write_config(setup, MANAGED + """
Match host *.internal
    ForwardAgent yes
""")

        assert setup.cleanup_config() is True

        result = setup.ssh_config_file.read_text()
        assert "Match host *.internal" in result
        assert "ForwardAgent yes" in result

    def test_multi_pattern_host_line_is_not_claimed(self, setup):
        """'Host a b' is not one of ours even when a pattern carries the prefix."""
        write_config(setup, MANAGED + """
Host cloudx-dev-web1 shortcut
    ForwardX11 no
""")

        assert setup.cleanup_config() is True
        assert "Host cloudx-dev-web1 shortcut" in setup.ssh_config_file.read_text()

    def test_comment_above_unmanaged_host_travels_with_it(self, setup):
        write_config(setup, MANAGED + """
# the jump box, do not delete
Host bastion
    HostName 10.0.0.1
""")

        setup.cleanup_config()

        result = setup.ssh_config_file.read_text()
        assert "# the jump box, do not delete" in result
        comment_at = result.index("# the jump box, do not delete")
        assert comment_at < result.index("Host bastion")

    def test_generated_banners_are_not_duplicated(self, setup):
        """Banners precede managed sections and must be regenerated, not stacked."""
        write_config(setup, MANAGED)

        setup.cleanup_config()
        once = setup.ssh_config_file.read_text()
        setup.cleanup_config()
        twice = setup.ssh_config_file.read_text()

        assert once == twice, "cleanup must be idempotent"
        assert twice.count("#  GLOBAL") == 1

    def test_unmanaged_entries_are_placed_last(self, setup):
        """A catch-all must not shadow our specific patterns after a rewrite."""
        write_config(setup, """Host *
    ServerAliveInterval 60

""" + MANAGED)

        setup.cleanup_config()

        result = setup.ssh_config_file.read_text()
        assert result.index("Host cloudx-dev-*") < result.index("Host *\n")

    def test_cleanup_writes_a_backup(self, setup):
        original = write_config(setup, MANAGED)

        setup.cleanup_config()

        backup = setup.ssh_config_file.with_suffix(".bak")
        assert backup.exists()
        assert backup.read_text() == original


class TestHyphenatedEnvironmentNames:
    """Defect 2: '\\w+' cannot match 'pre-prod', which deleted the section."""

    HYPHENATED = """Host cloudx-*
    User ec2-user

Host cloudx-pre-prod-*
    IdentityFile ~/.ssh/cloudX/cloudX
    ProxyCommand uvx cloudx-proxy connect %h %p --aws-env acme

Host cloudx-pre-prod-web1
    HostName i-0123456789abcdef0
"""

    def test_environment_block_survives_cleanup(self, setup):
        write_config(setup, self.HYPHENATED)

        assert setup.cleanup_config() is True

        result = setup.ssh_config_file.read_text()
        assert "Host cloudx-pre-prod-*" in result
        assert "Host cloudx-pre-*" not in result
        assert "IdentityFile ~/.ssh/cloudX/cloudX" in result
        assert "--aws-env acme" in result

    def test_host_is_filed_under_the_full_environment(self, setup):
        parsed = setup._parse_ssh_config(self.HYPHENATED)

        assert set(parsed["environments"]) == {"pre-prod"}
        assert "pre" not in parsed["environments"]
        lines = parsed["environments"]["pre-prod"]["lines"]
        assert "Host cloudx-pre-prod-web1" in lines

    def test_longest_declared_environment_wins(self, setup):
        """'cloudx-pre-prod-web1' is ambiguous; declared environments decide."""
        assert setup._environment_for_host(
            "cloudx-pre-prod-web1", ["pre-prod", "pre"]
        ) == "pre-prod"
        assert setup._environment_for_host(
            "cloudx-pre-prod-web1", ["pre"]
        ) == "pre"

    def test_falls_back_to_first_segment_when_undeclared(self, setup):
        assert setup._environment_for_host("cloudx-dev-web1", []) == "dev"
        assert setup._environment_for_host("cloudx-dev", []) is None


class TestEnvironmentNameCase:
    """Defect 3: 'Dev' and 'dev' produced two sections; ssh matches Host
    patterns case-sensitively, so neither resolved reliably."""

    def test_adding_a_host_reuses_the_existing_case(self, setup):
        config = write_config(setup, MANAGED)

        env = setup.resolve_environment_name("Dev")
        assert env == "dev"

        assert setup._add_host_entry(env, "i-00000000", "web2", config) is True

        result = setup.ssh_config_file.read_text()
        assert host_names(result).count("Host cloudx-dev-*") == 1
        assert "Host cloudx-Dev-*" not in result
        assert "Host cloudx-dev-web2" in result

    def test_add_host_entry_normalises_case_on_its_own(self, setup):
        """Even called directly with the wrong case, no second section appears."""
        config = write_config(setup, MANAGED)

        assert setup._add_host_entry("DEV", "i-00000000", "web2", config) is True

        result = setup.ssh_config_file.read_text()
        assert host_names(result).count("Host cloudx-dev-*") == 1
        assert "Host cloudx-dev-web2" in result

    def test_resolve_keeps_new_environment_untouched(self, setup):
        write_config(setup, MANAGED)
        assert setup.resolve_environment_name("Prod") == "Prod"

    def test_resolve_without_a_config_file(self, setup):
        assert setup.resolve_environment_name("dev") == "dev"

    def test_new_environment_section_records_its_display_name(self, setup):
        config = write_config(setup, MANAGED)

        setup._add_host_entry("Staging", "i-00000000", "web1", config)

        result = setup.ssh_config_file.read_text()
        assert "#  Staging" in result
        assert "Host cloudx-Staging-*" in result


class TestHostEntryUpdates:
    def test_existing_host_is_replaced_not_duplicated(self, setup):
        config = write_config(setup, MANAGED)

        assert setup._add_host_entry("dev", "i-99999999999999999", "web1", config) is True

        result = setup.ssh_config_file.read_text()
        assert host_names(result).count("Host cloudx-dev-web1") == 1
        assert "HostName i-99999999999999999" in result
        assert "HostName i-0123456789abcdef0" not in result

    def test_duplicate_host_entries_are_collapsed(self, setup):
        write_config(setup, MANAGED + """
Host cloudx-dev-web1
    HostName i-deadbeefdeadbeef0
""")

        setup.cleanup_config()

        result = setup.ssh_config_file.read_text()
        assert host_names(result).count("Host cloudx-dev-web1") == 1

    def test_inline_comment_on_a_host_line_is_kept(self, setup):
        write_config(setup, """Host cloudx-*
    User ec2-user

Host cloudx-dev-*
    ProxyCommand uvx cloudx-proxy connect %h %p

Host cloudx-dev-web1 # erik's box
    HostName i-0123456789abcdef0
""")

        setup.cleanup_config()

        assert "# erik's box" in setup.ssh_config_file.read_text()


class TestParseStructure:
    def test_lowercase_keyword_still_opens_a_block(self, setup):
        """SSH keywords are case-insensitive."""
        parsed = setup._parse_ssh_config("""host cloudx-*
    User ec2-user

host cloudx-dev-web1
    HostName i-0123456789abcdef0
""")

        assert parsed["global"] is not None
        assert "dev" in parsed["environments"]
        assert parsed["other"] == []

    def test_global_section_is_parsed(self, setup):
        parsed = setup._parse_ssh_config(MANAGED)

        assert "Host cloudx-*" in parsed["global"]
        assert "User ec2-user" in parsed["global"]

    def test_version_header_is_detected(self, setup):
        parsed = setup._parse_ssh_config(
            "# SSH Configuration - Managed by cloudx-proxy v1.2.3\n\n" + MANAGED
        )

        assert parsed["version"] == "# SSH Configuration - Managed by cloudx-proxy v1.2.3"

    def test_version_header_is_not_duplicated_when_first_block_is_foreign(self, setup):
        write_config(setup, """# SSH Configuration - Managed by cloudx-proxy v1.2.3

Host bastion
    HostName 10.0.0.1

""" + MANAGED)

        setup.cleanup_config()

        result = setup.ssh_config_file.read_text()
        assert result.count("Managed by cloudx-proxy") == 1

    def test_empty_config_parses(self, setup):
        parsed = setup._parse_ssh_config("")

        assert parsed["environments"] == {}
        assert parsed["global"] is None
        assert parsed["other"] == []

    def test_wildcard_host_below_an_environment_is_not_a_host_entry(self, setup):
        """'cloudx-dev-web*' is neither an environment pattern nor a host."""
        parsed = setup._parse_ssh_config(MANAGED + """
Host cloudx-dev-web*
    ForwardX11 no
""")

        assert len(parsed["other"]) == 1
        assert "Host cloudx-dev-web*" in parsed["other"][0]


class TestPreambleDirectives:
    """Directives above the first Host block apply to every host.

    They were dropped entirely by the rewrite - the same data-loss class this
    module exists to prevent, one level up from the Host blocks. They also
    cannot simply be appended: below a Host block they would silently narrow to
    whichever host came last.
    """

    PREAMBLE = """ServerAliveInterval 60
StrictHostKeyChecking ask

""" + MANAGED

    def test_top_level_directives_survive_cleanup(self, setup):
        write_config(setup, self.PREAMBLE)

        assert setup.cleanup_config() is True

        result = setup.ssh_config_file.read_text()
        assert "ServerAliveInterval 60" in result
        assert "StrictHostKeyChecking ask" in result

    def test_they_stay_above_the_first_host_block(self, setup):
        write_config(setup, self.PREAMBLE)
        setup.cleanup_config()

        result = setup.ssh_config_file.read_text()
        assert result.index("ServerAliveInterval") < result.index("Host cloudx-*")

    def test_comments_above_them_are_kept(self, setup):
        write_config(setup, "# my global defaults\nServerAliveInterval 60\n\n" + MANAGED)
        setup.cleanup_config()

        result = setup.ssh_config_file.read_text()
        assert "# my global defaults" in result

    def test_the_managed_by_header_is_not_duplicated_into_the_preamble(self, setup):
        write_config(
            setup,
            "# SSH Configuration - Managed by cloudx-proxy v0.17.1\n\n"
            "ServerAliveInterval 60\n\n" + MANAGED,
        )
        setup.cleanup_config()

        result = setup.ssh_config_file.read_text()
        assert result.count("Managed by cloudx-proxy") == 1

    def test_parse_exposes_the_preamble(self, setup):
        parsed = setup._parse_ssh_config(self.PREAMBLE)

        assert "ServerAliveInterval 60" in parsed["preamble"]
        assert "StrictHostKeyChecking ask" in parsed["preamble"]


class TestRewritesAreStableWithUnmanagedContent:
    """The generated section banner is a comment on the next read.

    Kept as one of the preserved block's leading comments it was re-emitted on
    every rewrite, so the file grew each time cleanup ran.
    """

    WITH_FOREIGN = MANAGED + """
# my jump box
Host bastion
    HostName 10.0.0.1

Match host *.internal
    ForwardAgent yes
"""

    def test_banner_is_not_duplicated_across_runs(self, setup):
        write_config(setup, self.WITH_FOREIGN)

        counts = []
        for _ in range(3):
            setup.cleanup_config()
            counts.append(setup.ssh_config_file.read_text().count("NOT MANAGED"))

        assert counts == [1, 1, 1], f"banner accumulated: {counts}"

    def test_repeated_cleanup_is_byte_stable(self, setup):
        write_config(setup, self.WITH_FOREIGN)

        setup.cleanup_config()
        first = setup.ssh_config_file.read_text()
        setup.cleanup_config()
        second = setup.ssh_config_file.read_text()
        setup.cleanup_config()
        third = setup.ssh_config_file.read_text()

        assert first == second == third

    def test_preserved_content_survives_repeated_runs(self, setup):
        write_config(setup, self.WITH_FOREIGN)

        for _ in range(3):
            setup.cleanup_config()

        result = setup.ssh_config_file.read_text()
        for kept in ("# my jump box", "Host bastion", "Match host *.internal", "ForwardAgent yes"):
            assert kept in result

    def test_preamble_and_unmanaged_together_are_stable(self, setup):
        write_config(setup, "ServerAliveInterval 60\n\n" + self.WITH_FOREIGN)

        setup.cleanup_config()
        first = setup.ssh_config_file.read_text()
        setup.cleanup_config()

        assert setup.ssh_config_file.read_text() == first
        assert "ServerAliveInterval 60" in first
        assert first.count("NOT MANAGED") == 1


class TestStripGeneratedBanners:
    def test_removes_a_generated_banner(self, setup):
        lines = [
            "# " + "=" * 78,
            "#  NOT MANAGED BY cloudx-proxy - PRESERVED AS-IS",
            "# " + "=" * 78,
            "",
            "# a real comment",
        ]

        assert setup._strip_generated_banners(lines) == ["", "# a real comment"]

    def test_keeps_ordinary_comments(self, setup):
        lines = ["# one", "# two", "# three"]

        assert setup._strip_generated_banners(lines) == lines


class TestManagedHostLinesShareOnePrefixCase:
    """ssh matches Host patterns case-sensitively.

    Blocks are recognised as ours case-insensitively, so a config carrying a
    stale `Host cloudx-*` from an older release was written back unchanged and
    then never matched `cloudX-dev-web1`. The generic block's `IdentitiesOnly
    yes` and `User ec2-user` silently stopped applying, so ssh offered every
    key in the agent and hit the server's MaxAuthTries before reaching the one
    just pushed - surfacing as "Too many authentication failures" on a
    connection that was otherwise healthy.
    """

    MIXED_CASE = """# SSH Configuration - Managed by cloudx-proxy v0.16.15

Host cloudx-*
    User ec2-user
    TCPKeepAlive yes
    IdentitiesOnly yes

Host cloudX-DTA-*
    IdentityFile ~/.ssh/cloudX/cloudX
    ProxyCommand uvx cloudX-proxy connect %h %p --profile cloudx

Host cloudX-DTA-unified
    HostName i-095f07267c26a685c
"""

    def uppercase_setup(self, tmp_path):
        ssh_dir = tmp_path / "cloudX"
        ssh_dir.mkdir(parents=True, exist_ok=True)
        (ssh_dir / "config").write_text(self.MIXED_CASE)
        return CloudXSetup(
            ssh_dir=str(ssh_dir), ssh_host_prefix="cloudX", non_interactive=True
        )

    def managed_host_lines(self, setup):
        return [
            line for line in setup.ssh_config_file.read_text().splitlines()
            if line.startswith("Host ")
        ]

    def test_adding_a_host_normalises_the_stale_generic_block(self, tmp_path):
        setup = self.uppercase_setup(tmp_path)

        setup.setup_ssh_config("DTA", "i-0123456789abcdef0", "web2")

        lines = self.managed_host_lines(setup)
        assert "Host cloudX-*" in lines
        assert "Host cloudx-*" not in lines

    def test_cleanup_normalises_it_too(self, tmp_path):
        setup = self.uppercase_setup(tmp_path)

        setup.cleanup_config()

        lines = self.managed_host_lines(setup)
        assert "Host cloudX-*" in lines
        assert "Host cloudx-*" not in lines

    def test_every_managed_host_line_uses_one_case(self, tmp_path):
        """The invariant: a written file never disagrees with itself."""
        setup = self.uppercase_setup(tmp_path)

        setup.setup_ssh_config("DTA", "i-0123456789abcdef0", "web2")

        for line in self.managed_host_lines(setup):
            assert line.startswith("Host cloudX-"), f"inconsistent prefix case: {line!r}"

    def test_the_generic_block_keeps_its_directives(self, tmp_path):
        """Normalising the header must not disturb what the block contains."""
        setup = self.uppercase_setup(tmp_path)

        setup.setup_ssh_config("DTA", "i-0123456789abcdef0", "web2")

        result = setup.ssh_config_file.read_text()
        for directive in ("User ec2-user", "TCPKeepAlive yes", "IdentitiesOnly yes"):
            assert directive in result

    def test_lowercase_invocation_normalises_the_other_way(self, tmp_path):
        ssh_dir = tmp_path / "cloudx"
        ssh_dir.mkdir(parents=True)
        (ssh_dir / "config").write_text("""Host cloudX-*
    User ec2-user
    IdentitiesOnly yes

Host cloudx-dev-*
    ProxyCommand uvx cloudx-proxy connect %h %p

Host cloudx-dev-web1
    HostName i-0123456789abcdef0
""")
        setup = CloudXSetup(
            ssh_dir=str(ssh_dir), ssh_host_prefix="cloudx", non_interactive=True
        )

        setup.cleanup_config()

        for line in self.managed_host_lines(setup):
            assert line.startswith("Host cloudx-"), f"inconsistent prefix case: {line!r}"


class TestNormalizeManagedHostLine:
    def test_wrong_case_prefix_is_corrected(self, setup):
        assert setup._normalize_managed_host_line("Host cloudX-dev-web1") == "Host cloudx-dev-web1"

    def test_correct_case_is_untouched(self, setup):
        assert setup._normalize_managed_host_line("Host cloudx-dev-web1") == "Host cloudx-dev-web1"

    def test_inline_comment_survives(self, setup):
        assert setup._normalize_managed_host_line(
            "Host cloudX-dev-web1 # erik's box"
        ) == "Host cloudx-dev-web1 # erik's box"

    def test_only_the_prefix_is_touched(self, setup):
        """A host whose own name contains the prefix spelling is not rewritten."""
        assert setup._normalize_managed_host_line(
            "Host cloudX-dev-cloudX-thing"
        ) == "Host cloudx-dev-cloudX-thing"

    def test_a_non_host_line_is_untouched(self, setup):
        assert setup._normalize_managed_host_line("    User ec2-user") == "    User ec2-user"
