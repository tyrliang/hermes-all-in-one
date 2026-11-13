"""A replaced container name must not redirect an existing test's lifecycle."""
import importlib.util
import json
from pathlib import Path
import re
import sys

import pytest

spec = importlib.util.spec_from_file_location(
    'functional_smoke_identity', Path(__file__).resolve().parents[1] / 'scripts/functional-smoke.py'
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class Containers:
    def __init__(self, root, remove_original):
        self.root = root
        self.remove_original = remove_original
        self.original_id, self.replacement_id = 'a' * 64, 'b' * 64
        self.original = self.state(self.original_id, 'original workspace')
        self.replacement = self.state(self.replacement_id, 'keep replacement workspace')
        self.replacement['memory'] = {'replacement fact': 'keep replacement memory'}
        self.by_id = {self.original_id: self.original}
        self.by_name = {'e2e-test': self.original_id}

    def state(self, identifier, contents):
        workspace = self.root / identifier / 'workspace.txt'
        workspace.parent.mkdir()
        workspace.write_text(contents)
        return {'workspace': workspace, 'memory': {}, 'execs': 0, 'restarts': 0}

    def create(self, request):
        return (self.original_id + '\n').encode()

    def resolve(self, target):
        identifier = self.by_name.get(target, target)
        if identifier not in self.by_id:
            raise RuntimeError('Original container no longer exists')
        return identifier, self.by_id[identifier]

    def reassign_name(self):
        self.by_name['e2e-test'] = self.replacement_id
        self.by_id[self.replacement_id] = self.replacement
        if self.remove_original:
            del self.by_id[self.original_id]
        else:
            self.by_name['e2e-test-previous'] = self.original_id

    def docker(self, args, data=None, **kwargs):
        if args[:2] == ['container', 'inspect']:
            identifier, state = self.resolve(args[-1])
            return json.dumps([{'Id': identifier, 'Config': {'Labels': {'hermes.smoke-test': 'true'}}}]).encode()
        if args[0] == 'rm':
            identifier, state = self.resolve(args[-1])
            del self.by_id[identifier]
            self.by_name = {name: current for name, current in self.by_name.items() if current != identifier}
            return b''
        if args[0] == 'restart':
            identifier, state = self.resolve(args[-1])
            state['restarts'] += 1
            return identifier.encode()
        if args[0] == 'logs':
            self.resolve(args[-1])
            return b''
        if args[0] != 'exec':
            raise AssertionError('Unexpected Docker operation')
        identifier, state = self.resolve(args[args.index('-w') + 2])
        state['execs'] += 1
        if data == runner.INSTALL.encode():
            self.reassign_name()
            return b'dependencies ready'
        if data == runner.HEALTH.encode():
            return b'healthy'
        if data == runner.MEMORY.encode():
            action, topic, code = args[-3:]
            if action == 'retain':
                state['memory'][topic] = code
            else:
                assert state['memory'].get(topic) == code
            return b'memory ready'
        if data is not None:
            return state['workspace'].read_bytes()
        prompt = args[-1]
        marker = re.search(r'workspace-smoke-[0-9a-f]+', prompt)
        if marker:
            state['workspace'].write_text(marker.group())
            return marker.group().encode()
        return next(iter(state['memory'].values())).encode()


def assert_replacement_untouched(backend):
    assert backend.by_name['e2e-test'] == backend.replacement_id
    assert backend.replacement_id in backend.by_id
    assert backend.replacement['execs'] == 0
    assert backend.replacement['restarts'] == 0
    assert backend.replacement['workspace'].read_text() == 'keep replacement workspace'
    assert backend.replacement['memory'] == {'replacement fact': 'keep replacement memory'}


def test_lifecycle_stays_with_original_id_when_name_moves_to_another_fixture(monkeypatch, tmp_path):
    backend = Containers(tmp_path, remove_original=False)
    monkeypatch.setattr(runner, 'fixture_operation', backend.create)
    monkeypatch.setattr(runner, 'docker', backend.docker)
    monkeypatch.setattr(sys, 'argv', ['functional-smoke.py', 'test'])

    runner.main()

    assert backend.original['restarts'] == 1
    assert backend.original_id not in backend.by_id
    assert_replacement_untouched(backend)


def test_removed_original_does_not_redirect_failure_cleanup_to_replacement(monkeypatch, tmp_path):
    backend = Containers(tmp_path, remove_original=True)
    monkeypatch.setattr(runner, 'fixture_operation', backend.create)
    monkeypatch.setattr(runner, 'docker', backend.docker)
    monkeypatch.setattr(sys, 'argv', ['functional-smoke.py', 'test'])

    with pytest.raises(RuntimeError, match='Original container no longer exists'):
        runner.main()

    assert_replacement_untouched(backend)
