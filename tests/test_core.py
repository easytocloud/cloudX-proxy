"""Tests for the SSM session relay in ``CloudXProxy.start_session``.

The stderr relay polled ``process.poll()`` inside a ``readline()`` loop. Once
stderr reached EOF, ``readline()`` returned immediately and forever while the
process was still running, spinning a core for the life of the SSH session
(measured at ~970k iterations and 1.6s of CPU across 2 wall seconds). It also
raised ``CalledProcessError(None)`` if it ever left the loop without a
returncode. Iterating the pipe and then waiting fixes both.
"""

import subprocess
import sys
import time
import types
from unittest import mock

import pytest

from cloudx_proxy.core import CloudXProxy, configure_logging


def make_proxy():
    """A CloudXProxy with just the attributes start_session touches."""
    proxy = CloudXProxy.__new__(CloudXProxy)
    proxy.dry_run = False
    proxy.instance_id = "i-0123456789abcdef0"
    proxy.port = 22
    proxy.profile = "cloudX"
    proxy.region = "eu-west-1"
    proxy.session = types.SimpleNamespace(region_name="eu-west-1")
    return proxy


def run_child(source, capture_kwargs=None):
    """Run start_session against a stub child process running `source`."""
    real_popen = subprocess.Popen

    def fake_popen(cmd, **kwargs):
        if capture_kwargs is not None:
            capture_kwargs["cmd"] = cmd
            capture_kwargs.update(kwargs)
        return real_popen(
            [sys.executable, "-c", source],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    # The AWS CLI is resolved on PATH before launching; stand in for it.
    with mock.patch("cloudx_proxy.core.shutil.which", lambda name: "/usr/bin/aws"), \
         mock.patch("subprocess.Popen", fake_popen):
        make_proxy().start_session()


class TestStderrRelay:
    def test_does_not_spin_when_stderr_closes_early(self):
        """The regression: stderr at EOF while the process is still alive."""
        import resource

        cpu_before = resource.getrusage(resource.RUSAGE_SELF).ru_utime
        started = time.time()

        run_child("import os, time; os.close(2); time.sleep(1)")

        cpu_used = resource.getrusage(resource.RUSAGE_SELF).ru_utime - cpu_before
        waited = time.time() - started

        assert waited >= 0.9, "should have waited for the child to exit"
        assert cpu_used < 0.2, f"relay burned {cpu_used:.2f}s of CPU busy-waiting"

    def test_stderr_is_relayed_to_our_stderr_never_stdout(self, capsys):
        """stdout is the SSH data stream; anything we print there corrupts it."""
        configure_logging(False)  # binds to the captured stderr

        run_child("import sys; sys.stderr.write('Starting session\\n')")

        captured = capsys.readouterr()
        assert "Starting session" in captured.err
        assert captured.out == ""

    def test_undecodable_stderr_does_not_crash(self):
        run_child(r"import sys; sys.stderr.buffer.write(b'\xff\xfe bad bytes\n')")

    def test_nonzero_exit_raises_with_the_real_returncode(self):
        with pytest.raises(subprocess.CalledProcessError) as excinfo:
            run_child("import sys; sys.exit(3)")

        assert excinfo.value.returncode == 3

    def test_clean_exit_does_not_raise(self):
        run_child("import sys; sys.stderr.write('done\\n')")

    def test_missing_aws_cli_is_reported(self, capsys):
        configure_logging(False)  # binds to the captured stderr

        with mock.patch("cloudx_proxy.core.shutil.which", lambda name: None), \
             pytest.raises(FileNotFoundError):
            make_proxy().start_session()

        captured = capsys.readouterr()
        assert "AWS CLI is required" in captured.err
        assert "getting-started-install" in captured.err
        assert captured.out == ""


class TestNoShellIsUsed:
    """The session used to launch with shell=True on Windows.

    That hands the joined command line to cmd.exe, where --profile and --region
    - which arrive from the SSH config's ProxyCommand and are not validated -
    would have been subject to shell metacharacter interpretation (CWE-78).
    """

    def test_popen_is_not_given_a_shell(self):
        captured = {}
        run_child("import sys; sys.exit(0)", capture_kwargs=captured)

        assert captured.get("shell") in (None, False), "the command must not go through a shell"

    def test_the_executable_is_a_resolved_path(self):
        captured = {}
        run_child("import sys; sys.exit(0)", capture_kwargs=captured)

        assert captured["cmd"][0] == "/usr/bin/aws"

    def test_arguments_are_passed_as_a_list_not_a_string(self):
        captured = {}
        run_child("import sys; sys.exit(0)", capture_kwargs=captured)

        cmd = captured["cmd"]
        assert isinstance(cmd, list)
        assert "ssm" in cmd
        assert "start-session" in cmd

    def test_a_metacharacter_in_the_profile_is_never_interpreted(self):
        """A hostile --profile in a ProxyCommand must reach aws as one argument."""
        captured = {}
        proxy = make_proxy()
        proxy.profile = 'evil & calc.exe'

        real_popen = subprocess.Popen

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
            captured.update(kwargs)
            return real_popen(
                [sys.executable, "-c", "import sys; sys.exit(0)"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

        with mock.patch("cloudx_proxy.core.shutil.which", lambda name: "/usr/bin/aws"), \
             mock.patch("subprocess.Popen", fake_popen):
            proxy.start_session()

        assert captured["cmd"][captured["cmd"].index("--profile") + 1] == 'evil & calc.exe'
        assert captured.get("shell") in (None, False)
