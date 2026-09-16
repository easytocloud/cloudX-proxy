"""get_instance_tags() hostname/environment resolution.

Older cloudX-instance.yaml versions set the Name tag to
cloudX-{env}-{hostname} (optionally " | {username}"); current versions set
Name to the plain hostname with no prefix. Both must resolve a hostname
without complaint - the absence of the legacy prefix is not itself a
problem. Environment must prefer the explicit cloudX:environment tag over
one parsed out of a legacy Name tag, and only speak up when the two
sources actively disagree.
"""

import pytest

from cloudx_proxy.setup import CloudXSetup


class FakeEC2Client:
    def __init__(self, tags):
        self._tags = tags

    def describe_instances(self, InstanceIds):
        return {
            "Reservations": [
                {"Instances": [{"Tags": [{"Key": k, "Value": v} for k, v in self._tags.items()]}]}
            ]
        }


class FakeSession:
    def __init__(self, tags):
        self._tags = tags

    def client(self, service_name):
        assert service_name == "ec2"
        return FakeEC2Client(self._tags)


@pytest.fixture
def setup(tmp_path):
    return CloudXSetup(ssh_config=str(tmp_path / "config"))


def get_tags(setup, monkeypatch, tags):
    monkeypatch.setattr(
        "cloudx_proxy.setup.boto3.Session", lambda *a, **k: FakeSession(tags)
    )
    return setup.get_instance_tags("i-0123456789abcdef0")


class TestPlainNameTag:
    """Current cloudX-instance.yaml: Name is the bare hostname, no prefix."""

    def test_hostname_from_plain_name_no_warning(self, setup, monkeypatch, capsys):
        environment, hostname = get_tags(
            setup, monkeypatch, {"Name": "erix", "cloudX:environment": "DTA"}
        )

        assert (environment, hostname) == ("DTA", "erix")
        out = capsys.readouterr().out
        assert "does not match" not in out
        assert "✗" not in out

    def test_hyphenated_plain_hostname_is_kept_whole(self, setup, monkeypatch):
        environment, hostname = get_tags(
            setup, monkeypatch, {"Name": "my-dev-box", "cloudX:environment": "OTA"}
        )

        assert (environment, hostname) == ("OTA", "my-dev-box")


class TestLegacyNameTag:
    """Older cloudX-instance.yaml: Name is cloudX-{env}-{hostname}."""

    def test_env_and_hostname_parsed_when_tag_absent(self, setup, monkeypatch):
        environment, hostname = get_tags(setup, monkeypatch, {"Name": "cloudX-OTA-web1"})

        assert (environment, hostname) == ("OTA", "web1")

    def test_username_suffix_is_stripped(self, setup, monkeypatch):
        environment, hostname = get_tags(
            setup, monkeypatch, {"Name": "cloudX-OTA-web1 | erik"}
        )

        assert (environment, hostname) == ("OTA", "web1")


class TestEnvironmentPrecedence:
    def test_tag_wins_and_conflict_is_flagged(self, setup, monkeypatch, capsys):
        environment, hostname = get_tags(
            setup, monkeypatch, {"Name": "cloudX-FOO-erik", "cloudX:environment": "BAR"}
        )

        assert environment == "BAR"
        assert hostname == "erik"
        out = capsys.readouterr().out
        assert "FOO" in out and "BAR" in out
        assert "✗" in out

    def test_agreement_is_not_flagged(self, setup, monkeypatch, capsys):
        environment, hostname = get_tags(
            setup, monkeypatch, {"Name": "cloudX-OTA-erik", "cloudX:environment": "OTA"}
        )

        assert (environment, hostname) == ("OTA", "erik")
        assert "✗" not in capsys.readouterr().out

    def test_environment_tag_alone_is_sufficient(self, setup, monkeypatch):
        environment, hostname = get_tags(
            setup, monkeypatch, {"Name": "erix", "cloudx:environment": "dta"}
        )

        assert (environment, hostname) == ("dta", "erix")

    def test_generic_environment_tag_is_last_resort(self, setup, monkeypatch):
        environment, hostname = get_tags(
            setup, monkeypatch, {"Name": "erix", "Environment": "legacy"}
        )

        assert (environment, hostname) == ("legacy", "erix")


class TestNothingToGoOn:
    def test_no_name_and_no_environment_tag(self, setup, monkeypatch):
        environment, hostname = get_tags(setup, monkeypatch, {})

        assert (environment, hostname) == (None, None)
