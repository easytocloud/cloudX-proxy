"""Shared pytest configuration."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    """Point the home directory at a throwaway one for every test.

    CloudXSetup resolves ~/.ssh/config through Path.home(). Without this a
    test that registers a host appends an ``Include`` for its temp directory
    to the developer's real ~/.ssh/config, and that temp config's
    ``ProxyCommand`` then shadows the real one on the next ssh connection.
    """
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
