#!/usr/bin/env python3
"""Recover source using only this escrowed kit, private roots, Git and restic."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from repository_bundle import BundleError, MAX_BUNDLE, SNAPSHOT, private_input, recover
from source_escrow import restore_file, roots


def restore(root_file, snapshot, destination):
    if not SNAPSHOT.fullmatch(snapshot):
        raise ValueError('a full source snapshot ID is required')
    root_file = private_input(root_file)
    values = roots(root_file)
    env = {**os.environ, **{k: v for k, v in values.items()
                          if k != 'SOURCE_ESCROW_REPOSITORY_ID'},
           'GOMEMLIMIT': '320MiB', 'GOMAXPROCS': '1'}

    def restic(*args):
        result = subprocess.run(['restic', '--no-cache', *args], env=env,
                                capture_output=True, timeout=600)
        if result.returncode:
            raise ValueError('source recovery failed; private output suppressed')
        return json.loads(result.stdout)

    if restic('cat', 'config')['id'] != values['SOURCE_ESCROW_REPOSITORY_ID']:
        raise ValueError('source repository identity differs from the independent root')
    snapshots = restic('snapshots', '--json', '--host', 'dholbeat-source-escrow',
                       '--tag', 'source-escrow')
    if not any(item.get('id') == snapshot for item in snapshots):
        raise ValueError('snapshot is absent or has the wrong purpose')
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise ValueError('destination must be a new clone in an existing directory')
    with tempfile.TemporaryDirectory(prefix='.source-bootstrap-', dir=destination.parent) as temporary:
        work = Path(temporary)
        for name, quota in (('repository.bundle', MAX_BUNDLE), ('manifest.json', 1024**2)):
            restore_file(snapshot, name, quota, env, work / name)
        # Neither a provider remote nor an original checkout can be fetched.
        os.environ['GIT_ALLOW_PROTOCOL'] = 'file'
        result = recover(work / 'repository.bundle',
                         json.loads((work / 'manifest.json').read_text()), destination)
    return {**result, 'snapshot_id': snapshot, 'temporary_bundle_removed': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-file', required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        print(json.dumps(restore(args.root_file, args.snapshot, args.destination), sort_keys=True))
    except (BundleError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        print('Independent source recovery failed; private output suppressed.',
              file=__import__('sys').stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
