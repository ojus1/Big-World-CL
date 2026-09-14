from copy import deepcopy
import unittest
from worldlab.workplace import Workplace


class Bank:
    def public(self, task_id):
        return {'instruction': 'Public brief for ' + task_id}


def decision(delegate=True, messages=None):
    return {'delegate': delegate, 'request': 'Please complete this task from its source files.',
            'working_notes': 'Check returned work before relying on it.', 'share_document_ids': [],
            'colleague_messages': messages or [], 'process_proposal': None}


def world(employees=2, days=5):
    workforce = [{'id': f'editor-{i}', 'role': 'Editor', 'department': 'Communications',
                  'language': 'en', 'sessions_per_day': 1} for i in range(employees)]
    schedule = [{'id': f'd{day}-{e["id"]}', 'day': day, 'day_order': index,
                 'employee_id': e['id'], 'task_id': f'case-{day}', 'due_day': day,
                 'split': 'probe' if day >= 2 else 'train', 'lineage_group': f'family-{day}'}
                for day in range(days) for index, e in enumerate(workforce)]
    return {'specification': {'days': days, 'feedback_delay': 1,
                             'workplace': {'max_attempts': 2, 'grace_days': 3}},
            'workforce': workforce, 'schedule': schedule}


def finish(workplace, employee, obligation, *, success=True):
    workplace.decide(employee, obligation, decision())
    session = f'{workplace.day}-{employee}-{obligation}'
    workplace.start(obligation, session)
    workplace.complete(obligation, session, {'success': success, 'quality_score': 1. if success else .4,
                                            'feedback': 'Accepted' if success else 'Please correct the source calculations.'})


class Tests(unittest.TestCase):
    def test_feedback_messages_and_future_work_obey_release_boundaries(self):
        w = Workplace(world())
        w.advance(0)
        before = w.view('editor-0', 'd0-editor-0', Bank())
        self.assertNotIn('case-1', str(before))
        w.decide('editor-0', 'd0-editor-0', decision(messages=[
            {'recipient': 'editor-1', 'text': 'Verify the totals.', 'document_ids': []}]))
        w.start('d0-editor-0', 'session-0')
        w.complete('d0-editor-0', 'session-0', {'success': False, 'quality_score': .4, 'feedback': 'Source total is wrong'})
        same_day = w.view('editor-1', 'd0-editor-1', Bank())
        self.assertEqual(same_day['received_colleague_messages'], [])
        self.assertEqual(w.state['employees']['editor-0']['released_feedback'], [])
        w.advance(1)
        next_day = w.view('editor-1', 'd0-editor-1', Bank())
        self.assertEqual(next_day['received_colleague_messages'][0]['text'], 'Verify the totals.')
        self.assertEqual(len(w.state['employees']['editor-0']['released_feedback']), 1)
        self.assertNotIn('d0-editor-0', w.available('editor-0'))  # Delayed rework, not immediate replay.
        w.advance(2)
        self.assertIn('d0-editor-0', w.available('editor-0'))

    def test_deferral_and_wrong_department_never_create_work_or_mutate_authority(self):
        definition = world()
        definition['workforce'][1]['department'] = 'Finance'
        w = Workplace(definition); w.advance(0)
        snapshot = deepcopy(w.state)
        with self.assertRaises(ValueError):
            w.decide('editor-0', 'd0-editor-0', decision(messages=[
                {'recipient': 'editor-1', 'text': 'Unknown shared private records', 'document_ids': []}]))
        self.assertEqual(w.state, snapshot)
        w.decide('editor-0', 'd0-editor-0', decision(False))
        self.assertEqual(w.summary()['work_attempts'], 0)
        self.assertEqual(w.available('editor-0'), [])
        with self.assertRaises(ValueError): w.start('d0-editor-0', 'unapproved-work')
        w.advance(1)
        self.assertIn('d0-editor-0', w.available('editor-0'))

    def test_bad_work_causes_rework_cost_and_reduces_later_on_time_fulfillment(self):
        results = []
        for initial_success in [True, False]:
            w = Workplace(world(employees=1))
            for day in range(5):
                w.advance(day)
                pending = w.available('editor-0')
                if pending: finish(w, 'editor-0', pending[0], success=initial_success or day > 0)
            for day in range(5, 10): w.advance(day)
            results.append(w.summary())
            restored = Workplace.replay(w.world, w.state['commands'])
            self.assertEqual(restored.state, w.state)
            seen = set()
            for event in w.state['events']:
                self.assertTrue(set(event['causes']) <= seen)
                seen.add(event['id'])
        control, failed = results
        self.assertEqual(control['probe_obligations'], failed['probe_obligations'])
        self.assertEqual(control['rework_attempts'], 0)
        self.assertEqual(failed['rework_attempts'], 1)
        self.assertGreater(control['probe_accepted_on_time_fraction'], failed['probe_accepted_on_time_fraction'])
        self.assertGreater(control['utility_units'], failed['utility_units'])

    def test_work_requires_unique_identity_and_days_wait_for_completion(self):
        w = Workplace(world()); w.advance(0)
        w.decide('editor-0', 'd0-editor-0', decision())
        w.start('d0-editor-0', 'once')
        with self.assertRaises(ValueError): w.advance(1)
        with self.assertRaises(ValueError):
            w.complete('d0-editor-0', 'once', {'success': False, 'quality_score': None, 'feedback': ''})
        w.complete('d0-editor-0', 'once', {'success': True, 'quality_score': 1., 'feedback': 'Accepted'})
        with self.assertRaises(ValueError):
            w.complete('d0-editor-0', 'once', {'success': True, 'quality_score': 1., 'feedback': 'Again'})
        w.decide('editor-1', 'd0-editor-1', decision())
        with self.assertRaises(ValueError): w.start('d0-editor-1', 'once')

    def test_large_workforce_keeps_all_obligations_in_the_denominator(self):
        w = Workplace(world(employees=100, days=20))
        for day in range(25): w.advance(day)
        report = w.summary()
        self.assertEqual(report['planned_obligations'], 2000)
        self.assertEqual(report['status_counts'], {'expired': 2000})
        self.assertEqual(report['probe_obligations'], 1800)
        self.assertEqual(report['probe_quality_mean'], 0)
        self.assertEqual(report['probe_accepted_on_time_fraction'], 0)


if __name__ == '__main__': unittest.main()
