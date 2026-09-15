"""Coverage counts remain distinct from samples, actual eligibility and outcomes."""
from copy import deepcopy
import tempfile
from pathlib import Path
import unittest

from scripts.report_worldlab_design import describe, snapshot
from scripts.source_world_calibration import save, sha
from worldlab.worlds import compile_world
from worldlab.validation_context import ISOLATED
from test_worldlab_worlds import SPEC
from test_worldlab_judge_adapter import Bank, Harness, Judge


class Tests(unittest.TestCase):
    def study(self):
        bank = Bank()
        spec = {**deepcopy(SPEC), 'validation_context': ISOLATED}
        return bank, {'worlds': [compile_world(bank, spec, seed, Harness(), Judge()) for seed in (211, 223)]}

    def test_repeated_probe_tasks_do_not_increase_lineage_count_or_independent_units(self):
        bank, study = self.study()
        for world in study['worlds']:
            probes = [s for s in world['schedule'] if s['split'] == 'probe']
            for slot in probes:
                slot.update(task_id=probes[0]['task_id'], lineage_group=probes[0]['lineage_group'])
        report = describe(study, bank)
        self.assertEqual(report['world_pairs'], 2)
        self.assertEqual(report['employee_world_instances'], 2)
        self.assertEqual(report['employee_world_instances_with_one_probe_lineage'], 2)
        self.assertEqual(report['coverage_per_arm_across_prepared_worlds']['probe']['scheduled_slots'], 4)
        self.assertEqual(report['planned_arriving_obligations_per_arm_across_worlds'], 20)
        self.assertEqual(report['planned_isolated_gate_descriptors_across_worlds'], 4)
        self.assertEqual(report['rows'][0]['coverage']['probe']['largest_lineage_fraction'], 1)
        self.assertFalse(report['confirmatory_readiness_established'])
        self.assertFalse(report['actual_update_eligibility_established'])

    def test_late_feedback_can_remove_hypothetical_training_supply(self):
        bank, study = self.study()
        world = study['worlds'][0]
        self.assertTrue(describe(study, bank)['rows'][0]['scheduled_learning_supply'][0]['hypothetical_supply_sufficient'])
        for slot in world['schedule']:
            if slot['split'] == 'train':
                slot['feedback_day'] = 100
        report = describe(study, bank)
        self.assertFalse(report['rows'][0]['scheduled_learning_supply'][0]['hypothetical_supply_sufficient'])
        self.assertEqual(report['scheduled_learner_updates'], 2)
        self.assertEqual(report['updates_with_sufficient_hypothetical_supply'], 1)

    def test_corrupt_lineages_duplicate_seeds_and_unbound_bank_are_rejected(self):
        for change in ('lineage', 'seed', 'bank', 'employee', 'phase'):
            with self.subTest(change=change):
                bank, study = self.study()
                world = study['worlds'][0]
                if change == 'lineage': world['schedule'][0]['lineage_group'] = 'unrelated'
                if change == 'seed': study['worlds'][1]['seed'] = world['seed']
                if change == 'bank': world['bank_manifest_sha256'] = 'changed'
                if change == 'employee': world['workforce'].append(deepcopy(world['workforce'][0]))
                if change == 'phase': next(s for s in world['schedule'] if s['split'] == 'probe')['day'] = 0
                with self.assertRaises(ValueError): describe(study, bank)

    def test_snapshot_is_frozen_design_only_and_never_reads_live_outcomes(self):
        bank, study = self.study()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save(root / 'STUDY.json', study)
            save(root / 'PREPARED.json', {'study_sha256': sha(root / 'STUDY.json')})
            (root / 'STATUS.json').write_text('not JSON: outcomes must not be read')
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            report = snapshot(root, bank)
            self.assertFalse(report['execution_inspected'])
            self.assertEqual(report['model_calls'], 0)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            study['worlds'][0]['seed'] = 999
            save(root / 'STUDY.json', study)
            with self.assertRaisesRegex(ValueError, 'Prepared study bytes changed'):
                snapshot(root, bank)


if __name__ == '__main__':
    unittest.main()
