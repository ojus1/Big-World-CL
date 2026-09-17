import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.source_world_calibration import save
from worldlab.worlds import prepare_study, execute_study
from worldlab.audit_reacting import replay_commands
from worldlab.attempts import task_instruction
from test_worldlab_worlds import Bank, Harness, Judge, Learning, SPEC


class Driver:
    def __init__(self, defer=False): self.views = []; self.closed = False; self.defer = defer
    def decide(self, view, key, validate):
        self.views.append(copy.deepcopy(view))
        value = {'delegate': not (self.defer and view['day'] == 0),
                 'request': 'Work on ' + view['substantive_work'], 'working_notes': 'Observed ' + str(view['day']),
                 'share_document_ids': [], 'colleague_messages': [], 'process_proposal': None}
        validate(value)
        return value
    def usage(self): return {'tokens': len(self.views), 'model_calls': len(self.views)}
    def close(self): self.closed = True


class Factory:
    def __init__(self, defer=False): self.drivers = []; self.defer = defer
    def identity(self): return {'name': 'fixture', 'defer': self.defer}
    def prepare(self, world): return {'fixture': world['seed']}
    def open(self, world, context, out):
        driver = Driver(self.defer); self.drivers.append(driver); return driver


class Tests(unittest.TestCase):
    def test_multiple_queued_delegations_bind_to_their_own_later_work_admissions(self):
        spec = copy.deepcopy(SPEC)
        spec['employees'].append({**spec['employees'][0], 'id': 'colleague'})
        spec['max_parallel_employees'] = 2
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'study'; factory = Factory()
            prepare_study(Bank(), spec, [211], Harness(), Judge(), Learning(), out, factory)
            def attempt(*args, **kw):
                value = {'status': 'completed', 'tokens': 1, 'model_calls': 1,
                         'grade': {'grading_complete': True, 'quality_score': 1., 'success': True, 'feedback': 'Done'}}
                save(kw['out'] / 'ATTEMPT.json', value)
                return value
            with patch('worldlab.reacting.execute_task', side_effect=attempt):
                execute_study(Bank(), Harness(), Judge(), Learning(), out, factory)
            study = json.loads((out / 'STUDY.json').read_text())
            state = json.loads((out / 'worlds/seed-211/no_learning/STATE.json').read_text())
            self.assertEqual([c['operation'] for c in state['workplace']['commands'][:5]],
                             ['advance', 'decide', 'decide', 'start', 'start'])
            replay_commands(Bank(), study['worlds'][0], state)

    def test_arrivals_and_capacity_are_independent_and_rework_is_reserved(self):
        spec = copy.deepcopy(SPEC)
        spec['employees'][0].update(sessions_per_day=2, arrivals_per_day=1)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'study'
            result = prepare_study(Bank(), spec, [211], Harness(), Judge(), Learning(), out, Factory())
            study = json.loads((out / 'STUDY.json').read_text())
            self.assertEqual(len(study['worlds'][0]['schedule']), 10)
            self.assertEqual(result['planned_obligations'], 20)
            self.assertEqual(result['planned_work_sessions'], 40)
            self.assertEqual(study['actor_reservations']['max_logical_interviews'], 80)
            from worldlab.contracts import Budget
            self.assertEqual(study['token_reservation_ceiling']['work_including_judges'],
                             40 * (Budget().total_tokens + Judge.max_tokens))
            with self.assertRaises(ValueError):
                prepare_study(Bank(), spec, [211], Harness(), Judge(), Learning(), Path(tmp) / 'fixed')

    def test_spare_capacity_preserves_arrivals_while_rework_competes_for_work(self):
        from worldlab.workplace import Workplace
        from worldlab.worlds import compile_world
        worlds = []
        for capacity in (1, 2):
            spec = copy.deepcopy(SPEC)
            spec['employees'][0].update(sessions_per_day=capacity, arrivals_per_day=1)
            world = compile_world(Bank(), spec, 211, Harness(), Judge())
            worlds.append(world)
            place = Workplace(world)
            for day in range(3):
                place.advance(day)
                for ordinal in range(capacity):
                    pending = place.available('writer')
                    if not pending: continue
                    oid = pending[0]; key = f'{day}-{ordinal}'
                    decision = Driver().decide(place.view('writer', oid, Bank()), key, lambda d: None)
                    place.decide('writer', oid, decision); place.start(oid, key)
                    place.complete(oid, key, {'success': day != 0, 'quality_score': 0. if day == 0 else 1., 'feedback': 'review'})
            self.assertEqual(place.summary()['work_attempts'], 3 if capacity == 1 else 4)
            self.assertEqual(place.state['obligations']['d002-writer-000']['attempts'], capacity - 1)
        self.assertEqual(worlds[0]['schedule'], worlds[1]['schedule'])

    def study(self, tmp, *, failure=False, defer=False):
        observed = []
        def attempt(bank, harness, judge, **kw):
            observed.append(kw)
            result = {'status': 'completed', 'tokens': 10, 'model_calls': 1,
                      'grade': {'grading_complete': True, 'quality_score': .5 if failure else 1.,
                                'success': not failure, 'feedback': 'observed feedback'}}
            save(Path(kw['out']) / 'ATTEMPT.json', result)
            return result
        out = Path(tmp) / 'study'; factory = Factory(defer)
        prepare_study(Bank(), SPEC, [211], Harness(), Judge(), Learning(), out, factory)
        with patch('worldlab.reacting.execute_task', side_effect=attempt):
            execute_study(Bank(), Harness(), Judge(), Learning(), out, factory)
        return out, factory, observed

    def test_native_driver_contract_and_causal_replay_with_later_skill_deployment(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, factory, observed = self.study(tmp)
            self.assertTrue(all(d.closed for d in factory.drivers))
            self.assertEqual(len(observed), 20)
            self.assertTrue(all('employee_message' in r for r in observed))
            world = json.loads((out / 'STUDY.json').read_text())['worlds'][0]
            for name in ['no_learning', 'fixture-learning']:
                state = json.loads((out / 'worlds/seed-211' / name / 'STATE.json').read_text())
                place = replay_commands(Bank(), world, state)
                self.assertEqual(place.summary()['probe_accepted_on_time_fraction'], 1.)
                self.assertTrue(all(f['release_day'] <= d['day'] for d in state['decisions']
                                    for f in d['view']['recent_observed_outcomes']))
            for item in observed:
                if '/fixture-learning/' in str(item['out']) and int(item['out'].name[1:4]) > 6:
                    self.assertIn('New skill', item['skill'])
                else: self.assertNotIn('New skill', item['skill'])

    def test_failure_and_deferral_change_future_work_while_retaining_probe_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _, observed = self.study(tmp, failure=True, defer=True)
            root = out / 'worlds/seed-211/no_learning'
            state = json.loads((root / 'STATE.json').read_text())
            report = json.loads((root / 'REPORT.json').read_text())
            self.assertFalse(state['decisions'][0]['decision']['delegate'])
            self.assertEqual(state['sessions'][0]['day'], 1)
            self.assertGreater(report['workplace']['rework_attempts'], 0)
            self.assertEqual(report['workplace']['probe_obligations'], 2)
            self.assertEqual(report['probe_accepted_on_time_fraction'], 0.)

    def test_causal_audit_detects_future_feedback_and_rewritten_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _, _ = self.study(tmp)
            world = json.loads((out / 'STUDY.json').read_text())['worlds'][0]
            state = json.loads((out / 'worlds/seed-211/no_learning/STATE.json').read_text())
            corrupt = copy.deepcopy(state)
            corrupt['decisions'][0]['view']['recent_observed_outcomes'] = [{'feedback': 'future'}]
            with self.assertRaises(ValueError): replay_commands(Bank(), world, corrupt)
            corrupt = copy.deepcopy(state)
            corrupt['sessions'][0]['employee_message'] = 'rewritten'
            with self.assertRaises(ValueError): replay_commands(Bank(), world, corrupt)

    def test_employee_message_preserves_original_requirements(self):
        original = 'Deliver original source requirements.'
        self.assertEqual(task_instruction(original), original)
        value = task_instruction(original, 'Employee context')
        self.assertIn(original, value)
        self.assertIn('Employee context', value)
        with self.assertRaises(ValueError): task_instruction(original, '')


if __name__ == '__main__': unittest.main()
