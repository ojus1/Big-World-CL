from pathlib import Path
import tempfile
import unittest
from scripts.source_world_calibration import save
from worldlab.adapters import load_adapter
from worldlab.worlds import prepare_study, execute_study
from test_worldlab_worlds import Bank, Harness, Judge, SPEC


class Tests(unittest.TestCase):
    def test_factory_config_is_bound_and_execution_rejects_change_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); config = root / 'learner.json'
            save(config, {'factory': 'test_worldlab_worlds:Learning', 'kwargs': {}})
            learner = load_adapter(config, 'learner')
            self.assertEqual(learner.identity()['name'], 'fixture-learning')
            self.assertIn('module_sha256', learner.identity()['operator_factory'])
            out = root / 'study'
            prepare_study(Bank(), SPEC, [211], Harness(), Judge(), learner, out)
            # Even an otherwise harmless configuration-byte change is distinct
            # from the experiment that was frozen before execution.
            config.write_text(config.read_text() + '\n')
            changed = load_adapter(config, 'learner')
            self.assertNotEqual(learner.identity(), changed.identity())
            with self.assertRaises(ValueError):
                execute_study(Bank(), Harness(), Judge(), changed, out)
            self.assertFalse((out / 'EXECUTION.json').exists())

    def test_wrong_contract_and_ambiguous_configuration_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'adapter.json'
            save(config, {'factory': 'worldlab.contracts:NoLearning', 'kwargs': {}})
            with self.assertRaises(ValueError): load_adapter(config, 'harness')
            with self.assertRaises(ValueError):
                prepare_study(Bank(), SPEC, [211], Harness(), Judge(), load_adapter(config, 'learner'), Path(tmp) / 'study')
            save(config, {'factory': 'worldlab.contracts:NoLearning', 'kwargs': {}, 'ignored': True})
            with self.assertRaises(ValueError): load_adapter(config, 'learner')


if __name__ == '__main__': unittest.main()
