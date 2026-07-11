"""Shared console report formatting helpers.

Keeps section-header and separator widths consistent across the
inspection utilities (depo_inspect.py, blob_inspect.py) so all reports
share the same visual style.
"""

WIDTH = 85


def print_banner(title, width=WIDTH, char="="):
    """Prints a title centered between two full-width separator lines."""
    print("")
    print(char * width)
    print(f"{title:^{width}}")
    print(char * width)


def print_rule(width=WIDTH, char="-"):
    """Prints a single full-width separator line."""
    print(char * width)
