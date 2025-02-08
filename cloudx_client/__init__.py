"""CloudX Client - Connect to EC2 instances via SSM for VSCode Remote SSH."""

from .core import CloudXClient
from ._version import __version__

__all__ = ["CloudXClient", "__version__"]
