"""Color output utilities for cloudx-proxy CLI.

Provides consistent colored output across all commands with automatic
no-color support for non-TTY environments.
"""

import sys
from typing import Optional


class Colors:
    """ANSI color codes for terminal output."""

    # Basic colors
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'

    # Styles
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'

    # Semantic colors
    SUCCESS = GREEN
    ERROR = RED
    WARNING = YELLOW
    INFO = CYAN
    PROMPT = YELLOW
    HEADER = BOLD + BLUE
    SECONDARY = GRAY

    # Reset
    RESET = '\033[0m'

    @staticmethod
    def is_tty() -> bool:
        """Check if output is going to a terminal."""
        return sys.stdout.isatty()

    @staticmethod
    def should_color() -> bool:
        """Determine if colored output should be used."""
        # Check environment variables
        no_color = sys.platform.startswith('win') or not Colors.is_tty()
        return not no_color


def colorize(text: str, color: str, bold: bool = False) -> str:
    """Apply color to text with automatic no-color support.

    Args:
        text: Text to colorize
        color: Color code from Colors class
        bold: Whether to make text bold

    Returns:
        Colored text if TTY, plain text otherwise
    """
    if not Colors.should_color():
        return text

    prefix = Colors.BOLD + color if bold else color
    return f"{prefix}{text}{Colors.RESET}"


def success(text: str, bold: bool = False) -> str:
    """Format success message in green."""
    return colorize(text, Colors.SUCCESS, bold)


def error(text: str, bold: bool = False) -> str:
    """Format error message in red."""
    return colorize(text, Colors.ERROR, bold)


def warning(text: str, bold: bool = False) -> str:
    """Format warning message in yellow."""
    return colorize(text, Colors.WARNING, bold)


def info(text: str, bold: bool = False) -> str:
    """Format info message in cyan."""
    return colorize(text, Colors.INFO, bold)


def header(text: str) -> str:
    """Format header text in bold blue."""
    return colorize(text, Colors.BLUE, bold=True)


def prompt(text: str) -> str:
    """Format prompt text in yellow."""
    return colorize(text, Colors.PROMPT, bold=False)


def secondary(text: str) -> str:
    """Format secondary text in gray."""
    return colorize(text, Colors.SECONDARY, bold=False)


def bold(text: str) -> str:
    """Make text bold."""
    if not Colors.should_color():
        return text
    return f"{Colors.BOLD}{text}{Colors.RESET}"


def status_symbol(status: Optional[bool]) -> str:
    """Get status symbol with color.

    Args:
        status: True for success (✓), False for failure (✗), None for neutral (○)

    Returns:
        Colored status symbol
    """
    if status is True:
        return success("✓")
    elif status is False:
        return error("✗")
    else:
        return "○"


def format_instance_id(instance_id: str) -> str:
    """Format instance ID with color."""
    return colorize(instance_id, Colors.YELLOW, bold=False)


def format_hostname(hostname: str) -> str:
    """Format hostname with color."""
    return colorize(hostname, Colors.CYAN, bold=False)


def format_path(path: str) -> str:
    """Format file path with color."""
    return colorize(path, Colors.GRAY, bold=False)


def format_command(command: str) -> str:
    """Format command text with color."""
    return colorize(command, Colors.CYAN, bold=True)
