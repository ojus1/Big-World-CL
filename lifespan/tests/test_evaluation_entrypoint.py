"""Exercise Python's -m dispatch without credentials, profiles or native work."""
from contextlib import redirect_stdout
import io
import runpy
import sys
import unittest
from unittest.mock import patch
import warnings

from lifespan.evaluation import runner


class CanonicalEntrypointTests(unittest.TestCase):
    def test_module_launch_uses_canonical_main_and_native_defaults(self):
        observed = []
        def canonical_probe():
            defaults = runner.run_experiment.__kwdefaults__
            observed.append({
                'actor_driver': defaults['actor_factory'].__module__ + '.' + defaults['actor_factory'].__name__,
                'executor': defaults['executor'].__module__ + '.' + defaults['executor'].__name__,
                'argv': sys.argv[1:],
            })
        # --help also makes the old local-main path exit before credentials,
        # even if a regression bypasses the canonical spy. MiroFish imports are
        # independently blocked before any provider/configuration access.
        with patch.object(runner, 'main', side_effect=canonical_probe) as main, \
                patch('lifespan.mirofish.imports', side_effect=AssertionError('Native imports forbidden')), \
                patch.object(sys, 'argv', ['lifespan.evaluation.runner', '--help']), \
                redirect_stdout(io.StringIO()), warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)  # Canonical module was deliberately preloaded.
            namespace = runpy.run_module('lifespan.evaluation.runner', run_name='__main__', alter_sys=True)
        main.assert_called_once_with()
        self.assertIsNot(namespace['NativeActors'], runner.NativeActors)
        self.assertEqual(namespace['NativeActors'].__module__, '__main__')
        self.assertEqual(observed, [{
            'actor_driver': 'lifespan.evaluation.runner.NativeActors',
            'executor': 'lifespan.evaluation.runtime.execute_case',
            'argv': ['--help'],
        }])


if __name__ == '__main__':
    unittest.main()
