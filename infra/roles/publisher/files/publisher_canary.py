#!/usr/bin/env python3
"""Bounded seven-day publisher capacity evidence; never admits real providers."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

STATE = Path('/var/lib/dholbeat/publisher/canary.json')
LOCK = Path('/run/lock/dholbeat-publisher-canary.lock')
SERVICES = {'postiz', 'postiz-postgres', 'postiz-redis', 'temporal',
            'temporal-postgres', 'temporal-elasticsearch'}
MIB = 1024**2
GIB = 1024**3
DURATION = 7 * 86400
MAX_GAP = 900


class CanaryError(RuntimeError):
    pass


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise CanaryError('capacity observation failed; private output suppressed')
    return result.stdout


def collect():
    ids = command(['docker', 'ps', '-aq', '--filter',
                   'label=com.docker.compose.project=dholbeat-publisher']).split()
    if len(ids) != 6:
        raise CanaryError('the exact six production containers are required')
    containers = json.loads(command(['docker', 'inspect', *ids]))
    result = {}
    for container in containers:
        service = container['Config']['Labels']['com.docker.compose.service']
        if service not in SERVICES or service in result:
            raise CanaryError('production service inventory differs')
        status = container['State']
        if not status.get('Running') or status.get('Health', {}).get('Status') != 'healthy':
            raise CanaryError('a production service is not healthy')
        name = container['Id']
        # These are read-only cgroup counters, without application credentials.
        raw = command(['docker', 'exec', name, 'sh', '-c',
                       'cat /sys/fs/cgroup/memory.current; '
                       'cat /sys/fs/cgroup/memory.peak; '
                       'cat /sys/fs/cgroup/memory.events; '
                       'cat /sys/fs/cgroup/pids.current'])
        lines = raw.splitlines()
        events = dict(line.split() for line in lines[2:-1])
        result[service] = {'id': name, 'started_at': status['StartedAt'],
                           'memory': int(lines[0]), 'memory_peak': int(lines[1]),
                           'oom': int(events['oom']), 'oom_kill': int(events['oom_kill']),
                           'oom_killed': status['OOMKilled'],
                           'restarts': container['RestartCount'], 'pids': int(lines[-1])}
    postiz = result['postiz']['id']
    tmp = command(['docker', 'exec', postiz, 'df', '-B1', '/tmp']).splitlines()[-1].split()
    redis = command(['docker', 'exec', result['postiz-redis']['id'], 'redis-cli', 'info'])
    info = dict(line.split(':', 1) for line in redis.splitlines() if ':' in line)
    disk = shutil.disk_usage('/')
    return {'services': result, 'tmp_used': int(tmp[2]), 'disk_used': disk.used,
            'disk_free': disk.free, 'redis_rss': int(info['used_memory_rss']),
            'redis_rewrites': int(info['aof_rewrites']),
            'redis_rewrite_running': int(info['aof_rewrite_in_progress'])}


def advance(state, sample, now, action='sample'):
    """Pure evaluator; failures and collected peaks survive future samples."""
    if state['status'] == 'failed':
        return state
    if now < state['last_epoch'] or now - state['last_epoch'] > MAX_GAP:
        state.update(status='failed', failure='monitoring continuity exceeded 15 minutes')
        return state
    state['maximum_sample_gap_seconds'] = max(state.get('maximum_sample_gap_seconds', 0), now - state['last_epoch'])
    previous = state.get('services', {})
    planned = state.get('maintenance_until', 0) >= now
    failures = []
    for service, metrics in sample['services'].items():
        prior = previous.get(service)
        if metrics['oom'] or metrics['oom_kill'] or metrics['oom_killed'] or metrics['restarts']:
            failures.append('OOM or unexpected container restart')
        if prior and metrics['id'] != prior['id']:
            failures.append('container replacement invalidated the measured deployment')
        if prior and metrics['started_at'] != prior['started_at'] and not planned:
            failures.append('container start without recorded maintenance')
        metrics['memory_peak'] = max(metrics['memory_peak'], (prior or {}).get('memory_peak', 0))
    peaks = state.setdefault('peaks', {})
    values = {'publisher_memory': sum(v['memory_peak'] for v in sample['services'].values()),
              'postiz_pids': sample['services']['postiz']['pids'], 'tmp_used': sample['tmp_used'],
              'disk_used': sample['disk_used'],
              'redis_rss': max(sample['redis_rss'], sample['services']['postiz-redis']['memory_peak'])}
    for key, value in values.items():
        peaks[key] = max(peaks.get(key, 0), value)
    state['minimum_disk_free'] = min(state.get('minimum_disk_free', sample['disk_free']), sample['disk_free'])
    limits = {'publisher_memory': 4608 * MIB, 'postiz_pids': 410,
              'tmp_used': 256 * MIB * 0.8, 'disk_used': 18 * GIB,
              'redis_rss': 230 * MIB}
    if any(peaks[key] >= limit for key, limit in limits.items()) or state['minimum_disk_free'] < 8 * GIB:
        failures.append('capacity stop threshold exceeded')
    state['redis_rewrite_observed'] = (state.get('redis_rewrite_observed', False)
                                      or sample['redis_rewrites'] > 0 or bool(sample['redis_rewrite_running']))
    state.update(last_epoch=now, samples=state['samples'] + 1, services=sample['services'])
    if action == 'maintenance-begin':
        state['maintenance_until'] = now + MAX_GAP
        state['maintenance_count'] = state.get('maintenance_count', 0) + 1
    elif action == 'maintenance-end':
        state['maintenance_until'] = 0
    if failures:
        state.update(status='failed', failure=failures[0])
    elif (now - state['start_epoch'] >= DURATION and state['samples'] >= DURATION // 300
          and state['redis_rewrite_observed'] and not state.get('maintenance_until')):
        state['status'] = 'complete'
    return state


def write(state):
    data = json.dumps(state, sort_keys=True).encode() + b'\n'
    if len(data) > 16384:
        raise CanaryError('capacity evidence exceeded its 16 KiB quota')
    STATE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.canary-', dir=STATE.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, STATE)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'sample', 'status', 'maintenance-begin', 'maintenance-end'])
    parser.add_argument('--confirm')
    args = parser.parse_args()
    with LOCK.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        now = time.time()
        if args.action == 'start':
            if args.confirm != 'START-PUBLISHER-CANARY' or STATE.exists():
                raise CanaryError('start requires explicit confirmation and no previous evidence')
            state = {'schema_version': 1, 'host_id': 'publish-1', 'status': 'active',
                     'start_epoch': now, 'deadline_epoch': now + DURATION, 'last_epoch': now,
                     'samples': 0, 'provider_admission': 'not-authorized'}
        elif not STATE.exists():
            print(json.dumps({'status': 'not-started'}))
            return
        else:
            state = json.loads(STATE.read_text())
        if state['status'] == 'complete':
            print(json.dumps({k: v for k, v in state.items() if k != 'services'}, sort_keys=True))
            return
        if args.action != 'status':
            try:
                state = advance(state, collect(), now, args.action)
            except (CanaryError, KeyError, ValueError, OSError, IndexError, subprocess.SubprocessError):
                if args.action == 'sample' and state.get('maintenance_until', 0) >= now:
                    state['maintenance_samples'] = state.get('maintenance_samples', 0) + 1
                else:
                    state.update(status='failed', failure='production capacity/health observation failed', last_epoch=now)
            write(state)
        print(json.dumps({k: v for k, v in state.items() if k != 'services'}, sort_keys=True))
        if state['status'] == 'failed':
            raise CanaryError('capacity canary failed; admission remains blocked')


if __name__ == '__main__':
    try:
        main()
    except (CanaryError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        print('Publisher capacity canary failed; inspect the bounded host evidence.', file=__import__('sys').stderr)
        raise SystemExit(1)
