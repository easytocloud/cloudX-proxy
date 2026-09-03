"""cloudx-proxy - SSH proxy connecting VSCode Remote SSH to EC2 via AWS SSM."""


def _resolve_version() -> str:
    """Determine the package version.

    ``_version.py`` is written by setuptools_scm at build time and is not
    committed, so it is absent in a plain source checkout. Fall back to the
    installed distribution metadata, and finally to a sentinel, so importing
    the package never fails merely because it has not been built.

    Returns:
        str: The package version
    """
    try:
        from ._version import __version__ as scm_version
        return scm_version
    except ImportError:
        pass

    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("cloudx-proxy")
    except PackageNotFoundError:
        return "0.0.0+unknown"


__version__ = _resolve_version()

__all__ = ['__version__']
