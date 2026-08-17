#!/usr/bin/env python3
"""Open a new host-key-verified SSH session and run a harmless probe."""

from __future__ import annotations

import argparse
from pathlib import Path
import socket

import paramiko


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--user", required=True)
    parser.add_argument("--identity-file", required=True, type=Path)
    parser.add_argument("--known-hosts-file", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()

    for label, path in (
        ("identity file", args.identity_file),
        ("known-hosts file", args.known_hosts_file),
    ):
        if not path.is_file():
            raise SystemExit(f"second connection probe failed: {label} is unavailable")

    client = paramiko.SSHClient()
    client.load_host_keys(str(args.known_hosts_file))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(
            hostname=args.host,
            port=args.port,
            username=args.user,
            key_filename=str(args.identity_file),
            allow_agent=False,
            look_for_keys=False,
            timeout=args.timeout,
            auth_timeout=args.timeout,
            banner_timeout=args.timeout,
        )
        _stdin, stdout, stderr = client.exec_command("/usr/bin/true", timeout=args.timeout)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            detail = stderr.read(256).decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"remote probe exited {exit_status}: {detail}")
    except (OSError, paramiko.SSHException, RuntimeError, socket.timeout) as error:
        raise SystemExit(f"second connection probe failed: {error}") from error
    finally:
        client.close()
    print("second connection probe passed")


if __name__ == "__main__":
    main()
