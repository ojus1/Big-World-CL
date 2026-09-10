"""Merged option propagation using filesystem fixtures, never native evidence."""
import json
import unittest

from lifespan.actor_contract import provenance
from lifespan.evaluation.protocol import ExperimentConfig
from lifespan.tests import test_evaluation_runner as fixtures


class OptionalContractIntegrationTests(unittest.TestCase):
    def test_both_opt_in_contracts_reach_their_harness_and_report(self):
        fixture = fixtures.OfflineRunnerIntegrationTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups); self.addCleanup(fixture.tearDown)
        actor = {'version': 'actor-json-v1', 'max_output_tokens': 512, 'timeout_seconds': 120}
        config = ExperimentConfig(days=8, seed=100, hermes_transport='nonstreaming',
                                  actor_output_contract=actor)
        with fixtures.offline_dependencies():
            report = fixture.run_offline('both-contracts', config, stop_after_sessions=1)
        root = fixture.root / 'both-contracts'
        manifest = json.loads((root / 'manifest.json').read_text())
        session = fixtures.read_checkpoint(root)['runner']['sessions'][0]
        self.assertEqual(fixtures.FakeActors.instances[-1].spec['actor_output_contract'], actor)
        self.assertEqual(session['transport_mode_for_fixture_audit'], 'nonstreaming')
        self.assertEqual(manifest['config'], config.public())
        self.assertEqual(manifest['actor_output_contract_provenance'], provenance(actor))
        for name in ('hermes_transport', 'hermes_transport_provenance', 'actor_output_contract_provenance'):
            self.assertEqual(report['provenance'][name], manifest[name])
        self.assertNotIn('actor_output_contract', ExperimentConfig().public())
        self.assertNotIn('hermes_transport', ExperimentConfig().public())


if __name__ == '__main__':
    unittest.main()
