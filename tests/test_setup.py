"""Tests for cloudx_proxy.setup.

These focus on the behaviour touched by the CodeQL quality cleanup:

- ``_create_1password_key`` was restructured to remove an unreachable
  statement; the "key created" path must still save the public key AND
  surface the SSH-agent reminder before returning ``True``.
- ``setup_aws_profile`` narrowed a bare ``except:`` to ``except Exception:``;
  a missing profile must still be handled, while ``KeyboardInterrupt`` must
  now propagate.
- ``validate_instance_id`` regression coverage.
"""

import pytest

from cloudx_proxy.setup import CloudXSetup


@pytest.fixture
def setup(tmp_path):
    """A CloudXSetup pointed at an isolated ssh dir (no real files touched)."""
    return CloudXSetup(
        profile="cloudX-test-user",
        ssh_key="testkey",
        ssh_dir=str(tmp_path / "ssh"),
        non_interactive=True,
    )


class TestValidateInstanceId:
    @pytest.mark.parametrize("instance_id", [
        "i-1234abcd",                    # 8 hex
        "i-0123456789abcdef0",           # 17 hex
        "i-ABCDEF0123456789A",           # uppercase accepted
    ])
    def test_valid(self, instance_id):
        assert CloudXSetup.validate_instance_id(instance_id) is True

    @pytest.mark.parametrize("instance_id", [
        "",
        None,
        "i-",
        "1234abcd",                      # missing prefix
        "i-1234abc",                     # 7 chars
        "i-1234abcde",                   # 10 chars (neither 8 nor 17)
        "i-0123456789abcdef0g",          # non-hex char
        "i-0123456789abcdefg",           # 17 chars but non-hex
    ])
    def test_invalid(self, instance_id):
        assert CloudXSetup.validate_instance_id(instance_id) is False


class TestCreate1PasswordKey:
    """Covers the restructured (previously unreachable) success path."""

    def _install_stubs(self, monkeypatch, setup, *, create_success=True,
                        save_success=True):
        import cloudx_proxy.setup as setup_mod

        calls = {"saved": [], "reminded": False}

        monkeypatch.setattr(setup_mod, "list_ssh_keys", lambda: [])
        monkeypatch.setattr(
            setup_mod, "get_vaults",
            lambda: [{"id": "vault-1", "name": "Private"}],
        )
        monkeypatch.setattr(
            setup_mod, "create_ssh_key",
            lambda title, vault: (create_success, "ssh-ed25519 AAAA...", "item-1"),
        )

        def fake_save(public_key, path):
            calls["saved"].append((public_key, path))
            return save_success

        monkeypatch.setattr(setup_mod, "save_public_key", fake_save)

        # Detect the reminder line (previously dead code after the returns).
        orig_print_status = setup.print_status

        def tracking_print_status(message, status=None, indent=0):
            if "enabled in 1Password's SSH agent" in message:
                calls["reminded"] = True
            return orig_print_status(message, status, indent)

        monkeypatch.setattr(setup, "print_status", tracking_print_status)

        setup.op_vault = "Private"
        return calls

    def test_success_saves_key_and_shows_reminder(self, monkeypatch, setup):
        calls = self._install_stubs(monkeypatch, setup)

        result = setup._create_1password_key()

        assert result is True
        assert len(calls["saved"]) == 1, "public key should be saved exactly once"
        assert calls["saved"][0][1].endswith("testkey.pub")
        assert calls["reminded"], "SSH-agent reminder must be shown (was unreachable)"

    def test_save_failure_returns_false_without_reminder(self, monkeypatch, setup):
        calls = self._install_stubs(monkeypatch, setup, save_success=False)

        result = setup._create_1password_key()

        assert result is False
        assert calls["reminded"] is False

    def test_create_failure_returns_false(self, monkeypatch, setup):
        calls = self._install_stubs(monkeypatch, setup, create_success=False)

        result = setup._create_1password_key()

        assert result is False
        assert calls["saved"] == [], "should not attempt to save when creation failed"


class TestSetupAwsProfileExceptionHandling:
    """The bare except was narrowed to Exception (issue #2 in CodeQL)."""

    def test_missing_profile_is_handled(self, monkeypatch, setup):
        import cloudx_proxy.setup as setup_mod

        def boom(*args, **kwargs):
            raise Exception("profile not found")

        monkeypatch.setattr(setup_mod.boto3, "Session", boom)
        # The recovery path shells out to `aws configure`; stub it so nothing
        # real runs. Session then raises again and the outer handler returns.
        monkeypatch.setattr(setup_mod.subprocess, "run", lambda *a, **k: None)

        # Should not raise (Exception is caught); returns a bool.
        result = setup.setup_aws_profile()
        assert isinstance(result, bool)

    def test_keyboard_interrupt_propagates(self, monkeypatch, setup):
        import cloudx_proxy.setup as setup_mod

        def interrupt(*args, **kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr(setup_mod.boto3, "Session", interrupt)

        # Previously a bare `except:` would have swallowed this.
        with pytest.raises(KeyboardInterrupt):
            setup.setup_aws_profile()
