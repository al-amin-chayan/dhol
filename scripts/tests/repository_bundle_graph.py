#!/usr/bin/env python3
"""Real Git outage recovery/dirty/lightweight/bad-digest regressions, no network."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('repository_bundle', ROOT / 'scripts/lib/repository_bundle.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


def rejection(operation):
    try:
        operation()
    except bundle.BundleError:
        return
    raise AssertionError('unsafe bundle operation was accepted')


def main():
    with tempfile.TemporaryDirectory(prefix='dholbeat-source-outage-') as temporary:
        root = Path(temporary)
        repository = root / 'original'
        repository.mkdir()
        bundle.git(repository, 'init', '--quiet', '--initial-branch=main')
        bundle.git(repository, 'config', 'user.name', 'Credential-free fixture')
        bundle.git(repository, 'config', 'user.email', 'fixture@example.invalid')
        bundle.git(repository, 'config', 'commit.gpgSign', 'false')
        bundle.git(repository, 'config', 'tag.gpgSign', 'false')
        bundle.git(repository, 'config', 'tag.forceSignAnnotated', 'false')
        (repository / 'desired.txt').write_text('reproducible state\n')
        bundle.git(repository, 'add', 'desired.txt')
        bundle.git(repository, 'commit', '--quiet', '-m', 'fixture source')
        tag = 'infra-prod-20260913-1'
        bundle.git(repository, 'tag', '-a', tag, '-m', 'reviewed fixture release')
        output = root / 'escrow'
        output.mkdir()
        manifest = bundle.create(repository, tag, output)
        bundle.git(repository, 'tag', 'infra-prod-20260913-2')
        rejection(lambda: bundle.create(repository, tag, output))
        bundle.git(repository, 'tag', '-d', 'infra-prod-20260913-2')
        (repository / 'dirty.txt').write_text('unreviewed')
        rejection(lambda: bundle.create(repository, tag, output))
        (repository / 'dirty.txt').unlink()
        bad = {**manifest, 'bundle_sha256': 'a' * 64}
        rejection(lambda: bundle.recover(output / 'repository.bundle', bad, root / 'bad'))
        # Simulate loss of GitHub and the only old clone; the bundle is now the
        # sole source. Recovery uses Git's file transport exclusively.
        shutil.rmtree(repository)
        recovered = root / 'recovered'
        receipt = bundle.recover(output / 'repository.bundle', manifest, recovered)
        assert receipt['github_required'] is False
        assert (recovered / 'desired.txt').read_text() == 'reproducible state\n'
        assert bundle.git(recovered, 'rev-parse', 'HEAD') == manifest['release_commit']
        rejection(lambda: bundle.recover(output / 'repository.bundle', manifest, recovered))
    print('real Git source-escrow outage/annotation/dirty/digest/cleanup regressions passed')


if __name__ == '__main__':
    main()
