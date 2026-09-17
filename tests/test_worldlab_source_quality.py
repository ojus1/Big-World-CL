import unittest
from types import SimpleNamespace

from scripts.source_world_calibration import read
from worldlab.source_quality import REGISTRY, exclusions


class SourceQualityTests(unittest.TestCase):
    def setUp(self):
        self.task = 'internal/euw_v1_fr_010'
        self.record = read(REGISTRY)['exclusions'][self.task]
        self.bank = SimpleNamespace(by_id={self.task: {'public_directory': 'public/' + self.task}},
            inventory={'public/' + self.task + '/' + name: {'sha256': value}
                       for name, value in self.record['files'].items()})

    def test_demonstrated_contradiction_is_excluded(self):
        self.assertIn('95 pallets', exclusions(self.bank, {'id': self.task})[0])
        for row in self.record['proof'].values():
            self.assertGreater(row['initial_palettes'], row['capacity_palettes'])

    def test_changed_or_missing_source_requires_requalification(self):
        self.bank.inventory.pop(next(iter(self.bank.inventory)))
        self.assertIn('requalification required', exclusions(self.bank, {'id': self.task})[0])

    def test_unreviewed_task_is_not_excluded_for_performance(self):
        self.assertEqual([], exclusions(self.bank, {'id': 'internal/unrelated'}))


if __name__ == '__main__':
    unittest.main()
