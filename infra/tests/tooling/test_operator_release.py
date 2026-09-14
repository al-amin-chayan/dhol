"""Release writes require a real reviewed promotion, not a self-declared tag."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('operator_release_test', ROOT / 'scripts/lib/operator_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
HEAD, REVIEWED, TREE = 'a' * 40, 'b' * 40, 'c' * 40
TAG = 'infra-prod-20260914-1'
PULL = {'draft': False, 'base': {'ref': 'main'}, 'head': {'ref': 'develop', 'sha': REVIEWED},
        'merge_commit_sha': HEAD, 'merged_at': '2026-09-14T00:00:00Z',
        'user': {'login': 'chayan-codex[bot]'},
        'labels': [{'name': 'area:infra'}, {'name': 'review:ready-for-ci'}]}
REVIEW = {'state': 'APPROVED', 'commit_id': REVIEWED, 'id': 1,
          'user': {'login': 'chayan-claude[bot]'}, 'submitted_at': '2026-09-13T23:59:00Z',
          'body': f'Review type: Baseline\nReviewer: Claude Code\nReviewed head: {REVIEWED}'}


def fixture(monkeypatch, *, pull=None, review=None, dirty=False, annotated=True, changed_tree=False):
    calls = []

    def run(argv):
        calls.append(argv)
        if argv[0].endswith('github-app-git'):
            assert argv == [str(release.ROOT / 'scripts/github-app-git'), 'fetch', '--no-prune',
                            'https://github.com/al-amin-chayan/dhol.git', 'main:refs/remotes/origin/main']
            return ''
        if argv[0].endswith('github-app-gh'):
            return json.dumps([[REVIEW if review is None else review]] if argv[-1].endswith('/reviews') else
                              PULL if pull is None else pull)
        args = argv[3:]
        if args == ['rev-parse', 'HEAD']:
            return HEAD
        if args == ['status', '--porcelain']:
            return ' M file' if dirty else ''
        if args[0] == 'cat-file':
            return 'tag' if annotated else 'commit'
        if args[0] == 'merge-base':
            return ''
        if args[0] == 'rev-parse':
            if args[1].endswith('^{tree}'):
                return 'd' * 40 if changed_tree and args[1].startswith(REVIEWED) else TREE
            return HEAD
        raise AssertionError(argv)

    monkeypatch.setattr(release, 'run', run)
    monkeypatch.delenv('CI', raising=False)
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    return calls


def test_reviewed_merge_preserves_exact_source_tree_and_own_app_identity(monkeypatch):
    calls = fixture(monkeypatch)
    assert release.verify(TAG, '100') == HEAD
    assert len([v for v in calls if 'github-app-gh' in v[0]]) == 2


@pytest.mark.parametrize('mutation', ['dirty', 'lightweight', 'tree', 'unmerged', 'wrong-base', 'wrong-merge',
                                    'no-approval', 'wrong-reviewer', 'wrong-reviewed-head', 'open-finding', 'CI'])
def test_self_claimed_or_stale_production_authorization_fails(monkeypatch, mutation):
    pull, review = deepcopy(PULL), deepcopy(REVIEW)
    if mutation == 'unmerged':
        pull['merged_at'] = None
    elif mutation == 'wrong-base':
        pull['base']['ref'] = 'develop'
    elif mutation == 'wrong-merge':
        pull['merge_commit_sha'] = 'e' * 40
    elif mutation == 'no-approval':
        review['state'] = 'COMMENTED'
    elif mutation == 'wrong-reviewer':
        review['user']['login'] = 'chayan-codex[bot]'
    elif mutation == 'wrong-reviewed-head':
        review['commit_id'] = HEAD
    elif mutation == 'open-finding':
        pull['labels'][1]['name'] = 'review:changes-requested'
    fixture(monkeypatch, pull=pull, review=review, dirty=mutation == 'dirty',
            annotated=mutation != 'lightweight', changed_tree=mutation == 'tree')
    if mutation == 'CI':
        monkeypatch.setenv('CI', 'true')
    with pytest.raises(ValueError):
        release.verify(TAG, '100')
