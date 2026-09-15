"""Capacity acceptance must reflect duration, observations and real limits."""

from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('publisher_canary', ROOT / 'infra/roles/publisher/files/publisher_canary.py')
canary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canary)


def state():
    return {'status': 'active', 'start_epoch': 0, 'last_epoch': 0, 'samples': 0}


def sample():
    return {'services': {s: {'id': s, 'started_at': 'original', 'memory': 100,
                            'memory_peak': 100, 'oom': 0, 'oom_kill': 0,
                            'oom_killed': False, 'restarts': 0, 'pids': 10}
                         for s in canary.SERVICES},
            'tmp_used': 100, 'disk_used': 12 * canary.GIB,
            'disk_free': 12 * canary.GIB, 'redis_rss': 100,
            'redis_rewrites': 0, 'redis_rewrite_running': 0}


def test_complete_requires_seven_days_and_rewrite_observation():
    evidence = state()
    for now in range(0, canary.DURATION + 1, 300):
        evidence = canary.advance(evidence, sample(), now)
    assert evidence['status'] == 'active'
    observation = sample()
    observation['redis_rewrites'] = 1
    assert canary.advance(evidence, observation, canary.DURATION + 300)['status'] == 'complete'


def test_duration_cannot_hide_a_gap_or_inadequate_observations():
    assert canary.advance(state(), sample(), canary.DURATION)['status'] == 'failed'
    evidence = state()
    evidence['last_epoch'] = canary.DURATION - 300
    observation = sample()
    observation['redis_rewrites'] = 1
    assert canary.advance(evidence, observation, canary.DURATION)['status'] == 'active'


@pytest.mark.parametrize('metric,value', [('oom', 1), ('oom_kill', 1), ('oom_killed', True), ('restarts', 1)])
def test_oom_and_restart_failures_are_sticky(metric, value):
    observation = sample()
    observation['services']['postiz'][metric] = value
    failed = canary.advance(state(), observation, 300)
    assert failed['status'] == 'failed'
    assert canary.advance(failed, sample(), 600)['status'] == 'failed'


@pytest.mark.parametrize('metric,value', [('tmp_used', 256 * canary.MIB),
    ('disk_used', 18 * canary.GIB), ('disk_free', 7 * canary.GIB), ('redis_rss', 230 * canary.MIB)])
def test_capacity_limits_stop_admission(metric, value):
    observation = sample()
    observation[metric] = value
    assert canary.advance(state(), observation, 300)['status'] == 'failed'


def test_process_and_memory_limits_and_peak_preservation():
    observation = sample()
    observation['services']['postiz']['pids'] = 410
    assert canary.advance(state(), observation, 300)['status'] == 'failed'
    observation = sample()
    observation['services']['postiz']['memory_peak'] = 4608 * canary.MIB
    assert canary.advance(state(), observation, 300)['status'] == 'failed'
    observation = sample()
    observation['services']['postiz']['memory_peak'] = 1000
    evidence = canary.advance(state(), observation, 300)
    evidence = canary.advance(evidence, sample(), 600)
    assert evidence['services']['postiz']['memory_peak'] == 1000


def test_only_bounded_recorded_maintenance_permits_container_start_changes():
    evidence = canary.advance(state(), sample(), 300, 'maintenance-begin')
    changed = sample()
    changed['services']['postiz']['started_at'] = 'backup-resume'
    resumed = canary.advance(deepcopy(evidence), changed, 500, 'maintenance-end')
    assert resumed['status'] == 'active' and resumed['maintenance_until'] == 0
    replaced = deepcopy(changed)
    replaced['services']['postiz']['id'] = 'replacement'
    assert canary.advance(deepcopy(evidence), replaced, 500, 'maintenance-end')['status'] == 'failed'
    assert canary.advance(deepcopy(evidence), changed, 1201)['status'] == 'failed'
    ordinary = canary.advance(state(), sample(), 300)
    assert canary.advance(ordinary, changed, 500)['status'] == 'failed'
