#!/usr/bin/env python3
"""Copy stdin to stdout and a file while enforcing an exact file-size limit."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit-bytes", required=True, type=int)
    args = parser.parse_args()
    if args.limit_bytes <= 0:
        parser.error("--limit-bytes must be positive")

    written = 0
    exceeded = False
    with args.output.open("xb") as handle:
        while chunk := sys.stdin.buffer.read(64 * 1024):
            sys.stdout.buffer.write(chunk)
            remaining = max(args.limit_bytes - written, 0)
            if remaining:
                saved = chunk[:remaining]
                handle.write(saved)
                written += len(saved)
            if len(chunk) > remaining:
                exceeded = True
        handle.flush()
    sys.stdout.buffer.flush()
    if exceeded:
        print(
            f"bounded evidence exceeded {args.limit_bytes} bytes: {args.output}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
