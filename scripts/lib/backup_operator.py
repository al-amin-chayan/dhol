#!/usr/bin/env python3
"""Run installed backup operations over pinned, key-only publish-1 SSH."""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def private_identity(raw):
    path = Path(raw).expanduser()
    identity = path.resolve()
    if any(part in {'github-agent-apps', 'github-app'} for part in identity.parts):
        raise ValueError('GitHub App identities cannot be used for server access')
    if path.is_symlink() or not identity.is_file() or identity.stat().st_mode & 0o777 != 0o600:
        raise ValueError('SSH identity requires a regular mode-0600 file')
    if identity.is_relative_to(ROOT):
        raise ValueError('SSH identities must remain outside the checkout')
    # Walk resolved ancestors: regular checkouts, linked worktrees (.git file),
    # and bare repositories are excluded without relying on ambient Git env.
    for parent in identity.parents:
        if ((parent / '.git').exists() or (parent / '.git').is_symlink()
                or ((parent / 'HEAD').is_file() and (parent / 'objects').is_dir()
                    and (parent / 'config').is_file())):
            raise ValueError('SSH identities must remain outside every Git checkout')
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'backup', 'status', 'restore-disposable'])
    parser.add_argument('--limit', required=True, choices=['publish-1'])
    parser.add_argument('--address', required=True)
    parser.add_argument('--identity-file', required=True)
    parser.add_argument('--known-hosts-file', required=True)
    parser.add_argument('--release')
    parser.add_argument('--review-pr')
    parser.add_argument('--snapshot')
    parser.add_argument('--name')
    parser.add_argument('--loopback-port', type=int, default=5200)
    parser.add_argument('--visibility-control-post-id')
    args = parser.parse_args()
    try:
        address = ipaddress.ip_address(args.address)
        if address not in ipaddress.ip_network('10.99.0.0/24'):
            raise ValueError('publish-1 administration must use its WireGuard subnet')
        identity = private_identity(args.identity_file)
        if os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS'):
            raise ValueError('backup operations are operator-only')
        if args.command == 'init':
            from operator_release import verify

            if not sys.stdin.isatty() or not args.release or not args.review_pr:
                raise ValueError('initialization requires a reviewed production release and founder confirmation')
            verify(args.release, args.review_pr)
            if input('Initialize the publish-1 private state repository? Type initialize-publish-1: ') != 'initialize-publish-1':
                raise ValueError('confirmation missing')
        argv = ['/usr/local/sbin/dholbeat-backup', args.command]
        if args.visibility_control_post_id:
            if args.command != 'backup' or not re.fullmatch('[a-zA-Z0-9_-]{1,80}', args.visibility_control_post_id):
                raise ValueError('Visibility control requires backup and a safe fixture post ID')
            argv += ['--visibility-control-post-id', args.visibility_control_post_id]
        if args.command == 'restore-disposable':
            if not re.fullmatch('[a-f0-9]{64}', args.snapshot or '') or not re.fullmatch('dholbeat-restore-[a-z0-9][a-z0-9-]{0,31}', args.name or ''):
                raise ValueError('full snapshot ID and a named disposable target are required')
            if not 5200 <= args.loopback_port <= 5299:
                raise ValueError('disposable loopback port must be reserved')
            argv += ['--snapshot', args.snapshot, '--name', args.name, '--loopback-port', str(args.loopback_port)]
        # Every remote token comes from fixed literals, validated names/hashes,
        # or an integer; SSH shell expansion cannot inject arbitrary commands.
        unit = 'dholbeat-backup-manual-' + str(os.getpid())
        remote = ['sudo', '-n', 'systemd-run', '--quiet', '--wait', '--pipe', '--collect', '--unit=' + unit,
            '--property=EnvironmentFile=/etc/dholbeat/restic.env', '--property=MemoryMax=256M',
            '--property=CPUQuota=50%', '--property=UMask=0077', *argv]
        known = Path(args.known_hosts_file).expanduser()
        if known.is_symlink() or not known.is_file() or not known.stat().st_size:
            raise ValueError('a verified known-hosts file is required')
        artifacts = ROOT / '.artifacts'
        if artifacts.is_symlink():
            raise ValueError('symlinked artifacts directory')
        artifacts.mkdir(exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix='backup-session-', dir=artifacts) as temporary:
            pin = Path(temporary) / 'known_hosts'
            shutil.copyfile(known, pin)
            pin.chmod(0o600)
            # Administrator name is the committed publish-1 baseline contract.
            baseline = (ROOT / 'infra/inventories/production/baseline/publish-1.yml').read_text()
            administrator = re.search(r'^admin:\s*\n\s+user:\s*([a-z_][a-z0-9_-]*)\s*$', baseline, re.MULTILINE)
            if not administrator:
                raise ValueError('administrator is missing from the committed contract')
            command = [str(ROOT / 'scripts/controller'), 'exec-ssh', '--known-hosts', str(pin.relative_to(ROOT)),
                '--identity', str(identity), '--confirm', 'production-host',
                'ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15',
                '-o', 'PasswordAuthentication=no', '-i', '/tmp/controller-home/.ssh/id_target',
                administrator[1] + '@' + str(address), *remote]
            result = subprocess.run(command, capture_output=True, timeout=7200)
            if result.returncode:
                raise ValueError('remote backup failed; private output suppressed')
            receipt = json.loads(result.stdout)
            if receipt.get('host_id') != 'publish-1':
                raise ValueError('remote backup receipt is not publish-1')
        print(json.dumps(receipt, sort_keys=True))
    except (ValueError, OSError, subprocess.SubprocessError):
        print('backup operator command failed; verify private inputs and the recovery runbook', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
