import copy
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from lifespan.evaluation.budget import ResponsesBudget
from lifespan.evaluation.runtime import install_skill
from scripts.source_world_calibration import read
from worldlab.skill_context import SkillContext, audit_context, audit_file


class Tests(unittest.TestCase):
    def setup_context(self, root, content='Check source evidence. Répondre en français.'):
        skill = install_skill(root / 'profile', content)
        reader = {'success': True, 'name': 'work-process',
                  'content': (root / 'profile/skills/work-process/SKILL.md').read_text()}
        context = SkillContext(root, skill, reader)
        meter = ResponsesBudget(max_model_calls=4, max_output_tokens=100, max_total_tokens=50000)
        context.bind(meter)
        return skill, context, meter

    def client(self, meter, seen):
        def dispatch(**kwargs):
            seen.append(kwargs)
            return {'status': 'completed', 'usage': {'input_tokens': 30, 'output_tokens': 5, 'total_tokens': 35}}
        client = SimpleNamespace(responses=SimpleNamespace(create=dispatch))
        return meter.wrap_client(client)

    def test_each_physical_request_including_recreated_client_has_auditable_context(self):
        for content in ('Seed skill', 'Learned candidate: cite complete sources.\nNe rien inventer.'):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); skill, context, meter = self.setup_context(root, content)
                seen = []
                self.assertFalse(context.loaded(meter.report()))
                for system in ('System A', 'Compacted system B'):
                    self.client(meter, seen).responses.create(instructions=system + context.block, input=[])
                self.assertEqual(len(seen), 2)
                self.assertEqual(meter.report()['charged_tokens'], 70)
                self.assertTrue(context.loaded(meter.report()))
                audit_file(root, skill, meter.report())
                self.assertEqual(set(read(context.path)['instructions'].values()), {r['instructions'] for r in seen})
                self.assertFalse(any('tool_calls' in r for r in seen))

    def test_missing_modified_or_duplicate_context_never_dispatches_and_latches(self):
        for kind in ('missing', 'modified', 'duplicate'):
            with tempfile.TemporaryDirectory() as tmp:
                skill, context, meter = self.setup_context(Path(tmp))
                seen, cancelled = [], []
                meter.on_block = cancelled.append
                client = self.client(meter, seen)
                instructions = {'missing': '', 'modified': context.block.replace('source', 'fake'),
                                'duplicate': context.block * 2}[kind]
                with self.assertRaises(ValueError): client.responses.create(instructions=instructions)
                with self.assertRaises(ValueError): client.responses.create(instructions=context.block)
                self.assertEqual(seen, [])
                self.assertEqual(meter.report()['physical_model_calls'], 0)
                self.assertEqual(meter.report()['charged_tokens'], 0)
                self.assertTrue(cancelled)
                self.assertFalse(context.loaded(meter.report()))

    def test_reader_and_auditor_reject_wrong_skill_and_tampered_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill, context, meter = self.setup_context(Path(tmp))
            for patch in ({'success': False}, {'name': 'other'}, {'content': 'wrong'}, {'error': 'failed'}):
                with self.assertRaises(ValueError): SkillContext(Path(tmp), skill, {**context.record['reader'], **patch})
            self.client(meter, []).responses.create(instructions=context.block)
            for mutation in ('instructions', 'binding', 'reader', 'error'):
                record, report = copy.deepcopy(context.record), meter.report()
                if mutation == 'instructions': record['instructions'][next(iter(record['instructions']))] += 'changed'
                if mutation == 'binding': report['operations'][0]['skill_context']['native_file_sha256'] = 'wrong'
                if mutation == 'reader': record['reader']['content'] += 'changed'
                if mutation == 'error': record['error'] = 'context missing'
                with self.assertRaises(ValueError): audit_context(record, skill, report)


if __name__ == '__main__': unittest.main()
