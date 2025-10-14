"""Command-line interface for the bulk CBCT inventory tool."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

if __package__ in {None, ""}:
    # Allow running as a standalone script without installing the package by
    # appending the project source directory to ``sys.path`` before importing.
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from pylinac_bulkcbct.inventory import DEFAULT_EXTENSIONS, build_inventory
else:
    from .inventory import DEFAULT_EXTENSIONS, build_inventory

LOG_LEVELS = {"critical", "error", "warning", "info", "debug"}


def configure_logging(level: str) -> None:
    """Configure root logging for the CLI."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover CBCT study directories for bulk processing with Pylinac.",
    )
    parser.add_argument(
        "root",
        type=Path,
        help="Root directory that contains CBCT study folders.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON inventory to. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--extensions",
        nargs="*",
        default=list(DEFAULT_EXTENSIONS),
        help="File extensions that should be considered image slices (defaults to .dcm and .ima).",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow symlinks while scanning for studies.",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=sorted(LOG_LEVELS),
        help="Logging verbosity level.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    inventory = build_inventory(
        args.root,
        extensions=args.extensions,
        follow_symlinks=args.follow_symlinks,
    )

    output = inventory.to_json()
    if args.output:
        args.output.write_text(output)
        logging.getLogger(__name__).info("Inventory written to %s", args.output)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
