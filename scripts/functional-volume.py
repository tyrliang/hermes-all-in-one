#!/usr/bin/env python3
"""Root-side Docker fixture transactions; JSON stdin, raw result bytes stdout."""
import contextlib
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid


LOCK_ROOT = Path('/run/lock/hermes-functional-smoke')
OWNER_LABEL = 'hermes.smoke-test'
INIT_LABEL = 'hermes.smoke-test.init-id'


def docker(args, data=None):
    """Run Docker without exposing arguments, fixture data, or container output on failure."""
    try:
        result = subprocess.run(
            ['docker', *args], input=data, capture_output=True, timeout=900,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError('Docker operation timed out; resources were left intact') from None
    except OSError:
        raise RuntimeError('Could not execute Docker') from None
    if result.returncode:
        raise RuntimeError('Docker operation failed; resources were left intact')
    return result.stdout


@contextlib.contextmanager
def volume_lock(volume):
    """Serialize cooperating transactions on the host, without waiting for another run."""
    LOCK_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity = hashlib.sha256(volume.encode('utf-8')).hexdigest()
    # Keep lock files permanently: unlinking would permit locks on different inodes.
    with (LOCK_ROOT / (identity + '.lock')).open('a') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Fixture volume transaction already in progress') from None
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def owned_labels(volume):
    metadata = json.loads(docker(['volume', 'inspect', volume]))[0]
    labels = metadata.get('Labels') or {}
    if labels.get(OWNER_LABEL) != 'true':
        raise RuntimeError('Not a smoke-test-owned volume')
    return labels


def require_unused(volume):
    consumers = docker([
        'container', 'ls', '--all', '--quiet', '--filter', 'volume=' + volume,
    ])
    if consumers.strip():
        raise RuntimeError('Fixture volume is attached to an existing container (running or stopped)')


def run(request):
    """Perform ownership checks and the mount under one host-side volume lock."""
    volume = request['volume']
    if not isinstance(volume, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]+', volume):
        raise RuntimeError('Invalid named fixture volume')
    action = request['action']
    if action not in ('init', 'run'):
        raise RuntimeError('Unknown fixture operation')
    with volume_lock(volume):
        if action == 'init':
            existing = docker([
                'volume', 'ls', '--format', '{{.Name}}', '--filter', 'name=' + volume,
            ]).decode().splitlines()
            if volume in existing:
                raise RuntimeError('Fixture volume already exists; use test, not init')
            init_id = uuid.uuid4().hex
            docker([
                'volume', 'create', '--label', OWNER_LABEL + '=true',
                '--label', INIT_LABEL + '=' + init_id, volume,
            ])
            # Docker can return a volume created concurrently by another process.
            # Only the exact creation token authorizes seeding or changing ownership.
            if owned_labels(volume).get(INIT_LABEL) != init_id:
                raise RuntimeError('Fixture volume creation ownership changed; refusing to seed')
            require_unused(volume)
            return docker([
                'run', '--rm', '-i', '--entrypoint', request['python'],
                '-v', volume + ':/opt/data', request['image'], '-c', request['seed'],
            ], json.dumps(request['fixture']).encode('utf-8'))
        args = request['args']
        if not isinstance(args, list) or not args or args[0] != 'run' or not all(isinstance(arg, str) for arg in args):
            raise RuntimeError('Fixture operation requires Docker run arguments')
        owned_labels(volume)
        require_unused(volume)
        # Docker attaches the container before returning, preserving the use lease
        # after this lock releases, including when the container later stops.
        return docker(args)


def main():
    try:
        result = run(json.load(sys.stdin))
        sys.stdout.buffer.write(result)
    except (RuntimeError, OSError, ValueError, KeyError, TypeError, IndexError) as error:
        # Request/JSON errors may embed fixture values; only our safe errors are shown.
        message = str(error) if isinstance(error, RuntimeError) else 'Invalid fixture request or host operation failure'
        print('[functional-volume] FAIL: ' + message, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
