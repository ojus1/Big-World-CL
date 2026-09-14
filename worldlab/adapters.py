"""Load operator-selected harness/learner factories without editing the runner.

These files select trusted Python code. They are never read from task workspaces.
Credentials belong in the factory's runtime environment, not its experiment file.
"""
from copy import deepcopy
import importlib
from pathlib import Path
from scripts.source_world_calibration import read, sha

METHODS = {'harness': ('identity', 'unsupported', 'run', 'audit_execution'),
           'learner': ('identity', 'update', 'audit_update')}


class ConfiguredAdapter:
    def __init__(self, delegate, descriptor):
        self.delegate, self.descriptor = delegate, descriptor

    def identity(self):
        original = self.delegate.identity()
        if not isinstance(original, dict) or not original.get('name') or 'operator_factory' in original:
            raise ValueError('Adapter identity needs a name and cannot override factory provenance')
        return {**deepcopy(original), 'operator_factory': deepcopy(self.descriptor)}

    def __getattr__(self, name):
        return getattr(self.delegate, name)


def load_adapter(path, kind):
    if kind not in METHODS:
        raise ValueError('Unknown adapter kind')
    path = Path(path).resolve()
    config = read(path)
    if set(config) != {'factory', 'kwargs'} or not isinstance(config['kwargs'], dict):
        raise ValueError('Adapter configuration requires exactly factory and kwargs')
    symbol = config['factory']
    if not isinstance(symbol, str) or symbol.count(':') != 1:
        raise ValueError('Factory must be a module:attribute reference')
    module_name, attribute = symbol.split(':')
    if not module_name or not attribute.isidentifier():
        raise ValueError('Invalid factory reference')
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute)
    source = Path(module.__file__).resolve()
    if not source.is_file() or not callable(factory):
        raise ValueError('Factory needs identifiable source and must be callable')
    delegate = factory(**config['kwargs'])
    if any(not callable(getattr(delegate, method, None)) for method in METHODS[kind]):
        raise ValueError('Adapter does not implement the ' + kind + ' contract')
    adapter = ConfiguredAdapter(delegate, {'kind': kind, 'factory': symbol,
        'module_sha256': sha(source), 'configuration_sha256': sha(path)})
    adapter.identity()  # Fail before any study preparation on malformed identity.
    return adapter
