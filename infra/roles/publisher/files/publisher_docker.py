#!/usr/bin/env python3
"""Serialize publisher Compose activation with its host kill switch."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Iterator, Sequence


DEFAULT_DOCKER = Path("/usr/bin/docker")
DEFAULT_MARKER = Path("/var/lib/dholbeat/publisher/kill-switch.json")
DEFAULT_LOCK = Path("/run/lock/dholbeat-publisher.lock")


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def is_compose_up(arguments: Sequence[str]) -> bool:
    try:
        compose_index = arguments.index("compose")
    except ValueError:
        return False
    return "up" in arguments[compose_index + 1 :]


def run_docker(
    arguments: Sequence[str],
    *,
    docker: Path = DEFAULT_DOCKER,
    marker: Path = DEFAULT_MARKER,
    lock: Path = DEFAULT_LOCK,
    execute: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> int:
    command = [str(docker), *arguments]
    if not is_compose_up(arguments):
        return execute(command, check=False).returncode
    with exclusive_lock(lock):
        if marker.is_file():
            print(
                "publisher Docker guard: kill switch is active; refusing Compose up",
                file=sys.stderr,
            )
            return 75
        return execute(command, check=False).returncode


def main() -> None:
    if not DEFAULT_DOCKER.is_file() or not os.access(DEFAULT_DOCKER, os.X_OK):
        print("publisher Docker guard: /usr/bin/docker is unavailable", file=sys.stderr)
        raise SystemExit(69)
    raise SystemExit(run_docker(sys.argv[1:]))


if __name__ == "__main__":
    main()
